import logging
from datetime import datetime, timedelta
from pathlib import Path
from collections.abc import Iterable
import dataclasses
import pathlib
from typing import Literal

from tqdm import tqdm
import numpy as np
import cf_units
import polars
from pyaro.timeseries.AutoFilterReaderEngine import (
    AutoFilterReader,
    AutoFilterEngine,
)
from pyaro.timeseries import (
    Reader,
    Data,
    Station,
)
import pyaro.timeseries


logger = logging.getLogger(__name__)


class EEAReaderException(Exception):
    pass


class EEAData(Data):
    def __init__(self, data, variable: str, metadata, unit: str | None = None) -> None:
        self._data = data
        self._variable = variable
        self._metadata = metadata
        self._unit = unit

    @property
    def _joined(self) -> polars.DataFrame:
        """Values and metadata are kept separated until needed to allow
        for lazy views
        """
        # Only keep values we need to reduce dataframe size
        joined = self._data.select("samplingpoint_id").join(
            self._metadata.select(
                "samplingpoint_id", "Longitude", "Latitude", "Altitude"
            ).unique("samplingpoint_id"),
            on="samplingpoint_id",
            how="left",
        )
        return joined

    @property
    def units(self) -> str:
        if self._unit is None:
            raise EEAReaderException("No units present in this dataset")
        return self._unit

    def keys(self):
        raise NotImplementedError

    def slice(self, index):
        return EEAData(
            self._data.filter(index), self._variable, self._metadata, self._unit
        )

    @property
    def variable(self) -> str:
        return self._variable

    @property
    def values(self) -> np.ndarray:
        return self._data["Value"].to_numpy()

    @property
    def stations(self) -> np.ndarray:
        station_names = self._metadata.select(
            "samplingpoint_id", "station"
        ).unique("samplingpoint_id")
        return (
            self._data.select("samplingpoint_id")
            .join(station_names, on="samplingpoint_id", how="left")
            .get_column("station")
            .to_numpy()
        )

    @property
    def station_ids(self) -> np.ndarray:
        return self._data["samplingpoint_id"].to_numpy()

    @property
    def latitudes(self) -> np.ndarray:
        return self._joined["Latitude"].to_numpy()

    @property
    def longitudes(self) -> np.ndarray:
        return self._joined["Longitude"].to_numpy()

    @property
    def altitudes(self) -> np.ndarray:
        return self._joined["Altitude"].to_numpy()

    @property
    def start_times(self) -> np.ndarray:
        return self._data["Start"].to_numpy()

    @property
    def end_times(self) -> np.ndarray:
        return self._data["End"].to_numpy()

    @property
    def flags(self) -> np.ndarray:
        def mapper(value: int) -> int:
            if value == 1:
                return pyaro.timeseries.Flag.VALID
            elif value == 2 or value == 3:
                return pyaro.timeseries.Flag.BELOW_THRESHOLD
            else:
                return pyaro.timeseries.Flag.INVALID

        valid = self._data["Validity"].map_elements(mapper, return_dtype=int)
        return valid.to_numpy()

    @property
    def standard_deviations(self) -> np.ndarray:
        return np.repeat(np.nan, self._nrecords())

    def _nrecords(self) -> int:
        return self._data.shape[0]

    def __len__(self) -> int:
        return self._nrecords()


def _validate_unit(units: Iterable[str], context: str = "") -> str | None:
    """Ensure a collection of unit strings are equivalent (allowing for
    cf_units-convertible variants), returning the representative unit.
    Returns None if no units were provided.
    """
    units = list(dict.fromkeys(units))
    if len(units) == 0:
        return None
    if len(units) > 1:
        base_unit = cf_units.Unit(units[0])
        for unit in units[1:]:
            if base_unit.convert(1, unit) != 1.0:
                raise EEAReaderException(
                    f"Multiple different units present{context} ({units[0]} and {unit})"
                )

    return units[0]


def _read(
    filepath: Path,
    filters: list[polars.Expr],
    known_unit: str | None = None,
) -> tuple[polars.DataFrame, str | None]:
    # Use Polars' native (non-pyarrow) parquet reader with expression-based
    # predicate/projection pushdown.
    # This is much faster (at least 2x) than using PyArrow's separate parquet reader.
    lf = polars.scan_parquet(filepath, low_memory=True, cache=False).select(
        "Samplingpoint",
        "Start",
        "End",
        "Value",
        "Unit",
        "Validity",
    )
    if filters:
        lf = lf.filter(polars.all_horizontal(filters))
    dataset = lf.collect().cast({"Value": polars.Float32})

    # Validate against any unit already established from previously read
    # files, so unit consistency is checked incrementally
    units = dataset["Unit"].unique()
    if known_unit is not None:
        units = [known_unit, *units]
    unit = _validate_unit(units, context=f" in {filepath}")
    dataset = dataset.drop("Unit")

    return dataset, unit


@dataclasses.dataclass
class _Filters:
    filters_hourly: list[polars.Expr]
    filters_daily: list[polars.Expr]
    time: pyaro.timeseries.Filter.TimeBoundsFilter | None


def _timefilter_hourly(
    filter: pyaro.timeseries.Filter.TimeBoundsFilter,
) -> list[polars.Expr]:
    # Time filtering might not be expressible as pushdown filters alone,
    # so we supply a coarse filter which should be filtered later on
    # TODO: Make this support more filtering whilst reading
    min_time, max_time = filter.envelope()

    # OBS: Critical assumption
    # Timezones for HOURLY data is given in UTC+1, but input filters
    # assume UTC. We must therefore add an hour for the envelope
    offset = timedelta(hours=1)
    min_time += offset
    min_time += offset

    return [
        polars.col("Start") >= min_time,
        polars.col("Start") <= max_time,
        polars.col("End") >= min_time,
        polars.col("End") <= max_time,
    ]


def _timefilter_daily(
    filter: pyaro.timeseries.Filter.TimeBoundsFilter,
) -> list[polars.Expr]:
    # Time filtering might not be expressible as pushdown filters alone,
    # so we supply a coarse filter which should be filtered later on
    # TODO: Make this support more filtering whilst reading
    min_time, max_time = filter.envelope()

    # OBS: Critical assumption
    # Timezones for daily data is given in a timezone
    # determined by the reporting country. As a coarse filter
    # use a safety margin.
    # The data will additionally be filtered at a later time
    # using the more accurate AutoFilterEngine filtering
    offset = timedelta(hours=26)

    return [
        polars.col("Start") >= (min_time - offset),
        polars.col("Start") <= (max_time + offset),
        polars.col("End") >= (min_time - offset),
        polars.col("End") <= (max_time + offset),
    ]


def _transform_filters(
    filters: Iterable[pyaro.timeseries.Filter.Filter],
) -> _Filters:
    validity_filter = polars.col("Validity") > 0

    filters_daily = [validity_filter]
    filters_hourly = filters_daily.copy()
    time_filter = None

    for filter in filters:
        if isinstance(filter, pyaro.timeseries.Filter.TimeBoundsFilter):
            if filter.has_envelope():
                filters_hourly.extend(_timefilter_hourly(filter))
                filters_daily.extend(_timefilter_daily(filter))
            time_filter = filter
        else:
            continue  # handled post-read

    return _Filters(
        filters_daily=filters_daily,
        filters_hourly=filters_hourly,
        time=time_filter,
    )


def _read_hourly_files(
    datapaths: list[Path],
    metadata: polars.DataFrame,
    filters: _Filters,
    station_ids: polars.DataFrame,
) -> tuple[polars.DataFrame, str | None]:
    id_dtype = station_ids["samplingpoint_id"].dtype
    dataset = polars.DataFrame(
        schema={
            # "Pollutant": polars.Int32,
            "Start": polars.Datetime("ns"),
            "End": polars.Datetime("ns"),
            "Value": polars.Float32,
            # "AggType": str,
            "Validity": polars.Int32,
            # "Verification": polars.Int32,
            # "ResultTime": datetime,
            # "DataCapture": datetime,
            # "FkObservationLog": str,
            "samplingpoint_id": id_dtype,
        }
    )

    unit = None
    pbar = tqdm(datapaths, disable=None)
    for file in pbar:
        pbar.set_description(f"Processing hourly {file.name:>54}")
        file_dataset, unit = _read(file, filters.filters_hourly, unit)
        # Map Samplingpoint -> samplingpoint_id per-file, while each file's
        # frame is still small, and drop the (comparatively large) string
        # column immediately.
        # A join() against the small station_ids lookup table is faster here than replace_strict(),
        # since each per-file frame (and thus the join's left side) is small.
        file_dataset = (
            file_dataset.with_columns(
                polars.col("Samplingpoint")
                .str.replace_many(["GI/", "/"], ["GB_", "_"])
                .alias("station")
            )
            .join(station_ids, on="station", how="left")
            .drop("Samplingpoint", "station")
        )
        dataset.vstack(file_dataset, in_place=True)

    dataset = dataset.rechunk()

    # OBS: Times are given in this timezone for non-daily observations
    # this assumption is also used for polars filtering
    original_timezone_for_hourly_data = "Etc/GMT+1"
    dataset = dataset.with_columns(
        polars.col("Start")
        .dt.replace_time_zone(original_timezone_for_hourly_data)
        .dt.convert_time_zone("UTC"),
        polars.col("End")
        .dt.replace_time_zone(original_timezone_for_hourly_data)
        .dt.convert_time_zone("UTC"),
    )

    return dataset, unit


def _read_daily_files(
    datapaths: list[Path],
    metadata: polars.DataFrame,
    filters: _Filters,
    station_ids: polars.DataFrame,
) -> tuple[polars.DataFrame, str | None]:
    dataset = polars.DataFrame(
        schema={
            "Samplingpoint": str,
            # "Pollutant": polars.Int32,
            "Start": polars.Datetime("ns"),
            "End": polars.Datetime("ns"),
            "Value": polars.Float32,
            # "AggType": str,
            "Validity": polars.Int32,
            # "Verification": polars.Int32,
            # "ResultTime": datetime,
            # "DataCapture": datetime,
            # "FkObservationLog": str,
        }
    )

    unit = None
    pbar = tqdm(datapaths, disable=None)
    for file in pbar:
        pbar.set_description(f"Processing daily {file.name:>54}")
        file_dataset, unit = _read(file, filters.filters_daily, unit)
        dataset.vstack(file_dataset, in_place=True)

    dataset = dataset.rechunk()

    # Join with metadata table to get latitude, longitude and altitude
    metadata = metadata.with_columns(
        (polars.col("Country Code") + "/" + polars.col("Sampling Point Id")).alias(
            "selector"
        ),
    ).select(
        [
            "selector",
            "Timezone",
        ]
    )

    dataset = dataset.join(metadata, left_on="Samplingpoint", right_on="selector", how="left")

    # Convert Start/End from each row's local reporting timezone to UTC.
    #
    # artition the rows by timezone, converting only the (much
    # smaller) per-timezone subset each time, then recombine. Peak memory is
    # now proportional to the dataset size once, not N times.
    tz_frames = []
    for tz in dataset["Timezone"].unique():
        if tz is None:
            # No matching metadata (e.g. no Timezone for this Samplingpoint):
            # keep the row but null out Start/End
            null_dt = polars.lit(None, dtype=polars.Datetime("ns", "UTC"))
            tz_frames.append(
                dataset.filter(polars.col("Timezone").is_null()).with_columns(
                    null_dt.alias("Start"),
                    null_dt.alias("End"),
                )
            )
            continue
        tz_frames.append(
            dataset.filter(polars.col("Timezone") == tz).with_columns(
                polars.col("Start").dt.replace_time_zone(tz).dt.convert_time_zone("UTC"),
                polars.col("End").dt.replace_time_zone(tz).dt.convert_time_zone("UTC"),
            )
        )
    if tz_frames:
        joined = polars.concat(tz_frames).drop("Timezone")
    else:
        # No rows at all (e.g. no daily files matched the given filters):
        joined = dataset.with_columns(
            polars.col("Start").cast(polars.Datetime("ns", "UTC")),
            polars.col("End").cast(polars.Datetime("ns", "UTC")),
        ).drop("Timezone")

    # Map Samplingpoint -> samplingpoint_id now that the (raw, "/"-separated)
    # Samplingpoint column is no longer needed for the timezone-selector join
    # above. Daily data volume is typically tiny compared to hourly, so the
    # memory/perf impact of doing this on the whole daily dataset here
    joined = (
        joined.with_columns(
            polars.col("Samplingpoint")
            .str.replace_many(["GI/", "/"], ["GB_", "_"])
            .alias("station")
        )
        .join(station_ids, on="station", how="left")
        .drop("Samplingpoint", "station")
    )

    return joined, unit


class EEAStation(Station):
    def __init__(self, fields: dict | None = None) -> None:
        self._fields = {
            "station": "",
            "latitude": float("nan"),
            "longitude": float("nan"),
            "altitude": float("nan"),
            "long_name": "",
            "country": "",
            "url": "",
            "station_area": "",
            "station_type": "",
            "display_name": "",
        }
        self._metadata = {}
        if fields:
            self.set_fields(fields)

    @property
    def station_area(self) -> str:
        self._fields["station_area"]

    @property
    def station_type(self) -> str:
        self._fields["station_type"]

    @property
    def display_name(self) -> str:
        self._fields["display_name"]


def _metadata_to_stations(metadata: polars.DataFrame) -> dict[str, EEAStation]:
    stations = metadata.with_columns(
        # polars.col("Sampling Point Id").alias("station"),
        polars.col("Latitude").alias("latitude"),
        polars.col("Longitude").alias("longitude"),
        polars.col("Altitude").alias("altitude"),
        polars.col("Country Code")
        .map_elements(_country_code_eea_to_iso, return_dtype=polars.String)
        .alias("country"),
        # polars.col("Source Data URL").alias("url"),
        polars.lit("").alias("url"),
        (polars.col("Country Code") + "/" + polars.col("Sampling Point Id")).alias(
            "long_name"
        ),
        polars.col("Air Quality Station Area").alias("station_area"),
        polars.col("Air Quality Station Type").alias("station_type"),
        polars.col("Air Quality Station EoI Code").alias("display_name"),
    ).select(
        [
            "station",
            "latitude",
            "longitude",
            "altitude",
            "country",
            "url",
            "station_area",
            "station_type",
            "long_name",
            "display_name",
        ]
    )
    station_dicts = {s["station"]: EEAStation(s) for s in stations.to_dicts()}
    return station_dicts


class EEATimeseriesReader(AutoFilterReader):
    def __init__(
        self,
        filename_or_obj_or_url,
        filters=[],
        station_area: str | list[str] = "all",
        station_type: str | list[str] = "all",
        dataset: Literal["verified", "unverified", "historical"] | None = None,
    ):
        self._set_filters(filters)
        if dataset is not None:
            logger.warning(
                "`dataset` keyword is deprecated, point directly to the catalog file"
            )
            filename_or_obj_or_url = (
                f"{filename_or_obj_or_url}/{dataset}/catalog.parquet"
            )
        metadata = polars.read_parquet(filename_or_obj_or_url)
        mod_time = pathlib.Path(filename_or_obj_or_url).stat().st_mtime
        mod_time = datetime.fromtimestamp(mod_time)
        self._revision = f"{mod_time:%Y-%m-%dT%H:%M:%S}"

        self._data_directory = pathlib.Path(filename_or_obj_or_url).parent

        if station_area != "all":
            if isinstance(station_area, str):
                station_area = [station_area]
            metadata = metadata.filter(
                polars.col("Air Quality Station Area").is_in(station_area)
            )
        if station_type != "all":
            if isinstance(station_type, str):
                station_type = [station_type]
            metadata = metadata.filter(
                polars.col("Air Quality Station Type").is_in(station_type)
            )

        keep_filters = []
        metadata = metadata.with_columns(
            (polars.col("Country Code") + "/" + polars.col("Sampling Point Id"))
            .str.replace("/", "_")
            .alias("station"),
        )
        samplingpoint_ids = metadata.select("station").unique().with_row_index(
            "samplingpoint_id"
        )
        metadata = metadata.join(samplingpoint_ids, on="station", how="left")
        for filter in self._get_filters():
            if isinstance(filter, pyaro.timeseries.Filter.CountryFilter):
                metadata = metadata.filter(
                    polars.col("Country Code")
                    .map_elements(_country_code_eea_to_iso, return_dtype=polars.String)
                    .map_elements(filter.has_country, return_dtype=bool)
                )
            elif isinstance(filter, pyaro.timeseries.Filter.StationReductionFilter):
                # intercepting this filter type as station filtering is done
                # more efficiently on the metadata instead of filtering
                # after reading all the data
                filtered_stations = filter.filter_stations(
                    _metadata_to_stations(metadata)
                )
                metadata = metadata.filter(
                    polars.col("station").is_in(filtered_stations.keys())
                )
            else:
                keep_filters.append(filter)
        self._set_filters(keep_filters)
        self._stations = metadata

    def metadata(self) -> dict[str, str]:
        metadata = dict()
        metadata["what"] = "EEA reader"
        metadata["download_url"] = "https://eeadmz1-downloads-webapp.azurewebsites.net/"
        metadata["revision"] = self._revision
        return metadata

    def _unfiltered_data(self, varname: str) -> Data:
        dataframe, metadata, unit = self._read(varname)
        return EEAData(dataframe, varname, metadata, unit)

    def _read(
        self,
        variable: str,
    ) -> tuple[polars.DataFrame, polars.DataFrame, str | None]:
        filters = _transform_filters(self._get_filters())

        # TODO: Enable depending on data wanted from e.g. time requested
        dataset = polars.DataFrame(
            schema={
                "Samplingpoint": str,
                "Pollutant": polars.Int32,
                "Start": polars.Datetime("ns"),
                "End": polars.Datetime("ns"),
                "Value": polars.Float32,
                # "AggType": str,
                "Validity": polars.Int32,
                # "Verification": polars.Int32,
                # "ResultTime": datetime,
                # "DataCapture": datetime,
                # "FkObservationLog": str,
            }
        )

        stations = self._stations.filter(polars.col("Air Pollutant").eq(variable))

        hourly_paths: list[Path] = [
            self._data_directory / path
            for path in stations.filter(polars.col("AggType") == "hour")["filename"]
        ]
        daily_paths: list[Path] = [
            self._data_directory / path
            for path in stations.filter(polars.col("AggType") == "day")["filename"]
        ]

        # Build the Samplingpoint -> samplingpoint_id lookup up front, so it
        # can be applied while reading the files.
        station_ids = self._stations.select(
            "station", "samplingpoint_id"
        ).unique("station")

        hourly_dataset, hourly_unit = _read_hourly_files(
            hourly_paths,
            self._stations,
            filters,
            station_ids,
        )
        if len(daily_paths) == 0:
            dataset = hourly_dataset
            unit = hourly_unit
        else:
            daily_dataset, daily_unit = _read_daily_files(
                daily_paths,
                self._stations,
                filters,
                station_ids,
            )
            dataset = hourly_dataset.vstack(daily_dataset)
            # Drop references to the pre-vstack frames 
            del hourly_dataset, daily_dataset
            unit = _validate_unit(
                [u for u in (hourly_unit, daily_unit) if u is not None],
                context=f" for variable {variable}",
            )

        return dataset, stations, unit

    def _unfiltered_variables(self) -> list[str]:
        return list(self._stations["Air Pollutant"].unique())

    def _unfiltered_stations(self) -> dict[str, Station]:
        return _metadata_to_stations(self._stations)

    def close(self) -> None:
        pass


class EEATimeseriesEngine(AutoFilterEngine):
    def description(self) -> str:
        return """EEA reader for parquet files

Read and filter hourly data from EEA stations using the unverified dataset.

Files must be downloaded from https://eeadmz1-downloads-webapp.azurewebsites.net/. The data
should be indexed using a catalog file in the parquet format.

EEA country codes might differ from pyaro country codes. This reader will map from EEA to ISO2
and only expectes ISO2 codes e.g. UK instead of GB

Data can be downloaded using the airbase tool (https://github.com/JohnPaton/airbase/)
OBS: Must use github version, pypi version does not download parquet files yet

airbase unverified --path datadir/unverified/hourly -p SO2 -p PM10 -p O3 -p NO2 -p CO -p NO -p PM2.5 -F hourly --metadata --overwrite
"""

    def url(self) -> str:
        return "https://github.com/metno/pyaro-readers"

    def reader_class(self) -> Reader:
        return EEATimeseriesReader


def _country_code_eea_to_iso(country: str) -> str:
    """ISO 3166-1 alpha-2 mappings for countries in EEA"""
    if country == "GB":
        return "UK"
    return country


def _country_code_iso_to_eea(country: str) -> str:
    """ISO 3166-1 alpha-2 mappings for countries in EEA"""
    if country == "UK":
        return "GB"
    return country
