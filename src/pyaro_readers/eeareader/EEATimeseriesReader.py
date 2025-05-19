import logging
from datetime import datetime, timedelta
from pathlib import Path
from collections.abc import Iterable
import dataclasses
import pathlib
from functools import cached_property
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
    def __init__(self, data, variable: str, metadata) -> None:
        self._data = data
        self._variable = variable
        self._metadata = metadata

    @cached_property
    def _joined(self) -> polars.DataFrame:
        """Values and metadata are kept separated until needed to allow
        for lazy views
        """
        # Only keep values we need to reduce dataframe size
        joined = self._data.select("station").join(
            self._metadata.with_columns(
                (polars.col("Country Code") + "/" + polars.col("Sampling Point Id"))
                .str.replace("/", "_")
                .alias("station")
            )
            .select("station", "Longitude", "Latitude", "Altitude")
            .unique("station"),
            on="station",
        )
        return joined

    @cached_property
    def units(self) -> str:
        units = self._data["Unit"].unique()
        if len(units) == 0:
            raise EEAReaderException("No units present in this dataset")
        elif len(units) != 1:
            base_unit = cf_units.Unit(units[0])
            for unit in units[1:]:
                if base_unit.convert(1, unit) != 1.0:
                    raise EEAReaderException(
                        f"Multiple different units present in this dataset ({units[0]} and {unit})"
                    )

        return units[0]

    def keys(self):
        raise NotImplementedError

    def slice(self, index):
        return EEAData(self._data.filter(index), self._variable, self._metadata)

    @property
    def variable(self) -> str:
        return self._variable

    @property
    def values(self) -> np.ndarray:
        return self._data["Value"].to_numpy()

    @property
    def stations(self) -> np.ndarray:
        return self._data["station"].to_numpy()

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


def _read(filepath: Path, pyarrow_filters) -> polars.DataFrame:
    return polars.read_parquet(
        filepath,
        use_pyarrow=True,
        pyarrow_options={"filters": pyarrow_filters},
        columns=[
            "Samplingpoint",
            "Start",
            "End",
            "Value",
            "Unit",
            "Validity",
        ],
    ).cast({"Value": polars.Float32})


@dataclasses.dataclass
class _Filters:
    pyarrow_filters_hourly: list[tuple[str, str, str | datetime]]
    pyarrow_filters_daily: list[tuple[str, str, str | datetime]]
    time: pyaro.timeseries.Filter.TimeBoundsFilter | None


def _pyarrow_timefilter_hourly(
    filter: pyaro.timeseries.Filter.TimeBoundsFilter,
) -> list[tuple[str, str, datetime]]:
    # Time filtering might not be expressible as pyarrow filters alone,
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
        ("Start", ">=", min_time),
        ("Start", "<=", max_time),
        ("End", ">=", min_time),
        ("End", "<=", max_time),
    ]


def _pyarrow_timefilter_daily(
    filter: pyaro.timeseries.Filter.TimeBoundsFilter,
) -> list[tuple[str, str, datetime]]:
    # Time filtering might not be expressible as pyarrow filters alone,
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
        ("Start", ">=", min_time - offset),
        ("Start", "<=", max_time + offset),
        ("End", ">=", min_time - offset),
        ("End", "<=", max_time + offset),
    ]


def _transform_filters(
    filters: Iterable[pyaro.timeseries.Filter.Filter],
) -> _Filters:
    validity_filter = ("Validity", ">", 0)

    pyarrow_filters_daily = [validity_filter]
    pyarrow_filters_hourly = pyarrow_filters_daily.copy()
    time_filter = None

    for filter in filters:
        if isinstance(filter, pyaro.timeseries.Filter.TimeBoundsFilter):
            if filter.has_envelope():
                pyarrow_filters_hourly.extend(_pyarrow_timefilter_hourly(filter))
                pyarrow_filters_daily.extend(_pyarrow_timefilter_daily(filter))
            time_filter = filter
        else:
            continue  # handled post-read

    return _Filters(
        pyarrow_filters_daily=pyarrow_filters_daily,
        pyarrow_filters_hourly=pyarrow_filters_hourly,
        time=time_filter,
    )


def _read_hourly_files(
    datapaths: list[Path],
    metadata: polars.DataFrame,
    filters: _Filters,
) -> polars.DataFrame:
    dataset = polars.DataFrame(
        schema={
            "Samplingpoint": str,
            # "Pollutant": polars.Int32,
            "Start": polars.Datetime("ns"),
            "End": polars.Datetime("ns"),
            "Value": polars.Float32,
            "Unit": str,
            # "AggType": str,
            "Validity": polars.Int32,
            # "Verification": polars.Int32,
            # "ResultTime": datetime,
            # "DataCapture": datetime,
            # "FkObservationLog": str,
        }
    )

    pbar = tqdm(datapaths, disable=None)
    for file in pbar:
        pbar.set_description(f"Processing hourly {file.name:>54}")
        dataset.vstack(_read(file, filters.pyarrow_filters_hourly), in_place=True)

    dataset.rechunk()

    # OBS: Times are given in this timezone for non-daily observations
    # this assumption is also used for pyarrow filtering
    original_timezone_for_hourly_data = "Etc/GMT+1"
    dataset = dataset.with_columns(
        polars.col("Start")
        .dt.replace_time_zone(original_timezone_for_hourly_data)
        .dt.convert_time_zone("UTC"),
        polars.col("End")
        .dt.replace_time_zone(original_timezone_for_hourly_data)
        .dt.convert_time_zone("UTC"),
    )

    return dataset


def _read_daily_files(
    datapaths: list[Path],
    metadata: polars.DataFrame,
    filters: _Filters,
) -> polars.DataFrame:
    dataset = polars.DataFrame(
        schema={
            "Samplingpoint": str,
            # "Pollutant": polars.Int32,
            "Start": polars.Datetime("ns"),
            "End": polars.Datetime("ns"),
            "Value": polars.Float32,
            "Unit": str,
            # "AggType": str,
            "Validity": polars.Int32,
            # "Verification": polars.Int32,
            # "ResultTime": datetime,
            # "DataCapture": datetime,
            # "FkObservationLog": str,
        }
    )

    pbar = tqdm(datapaths, disable=None)
    for file in pbar:
        pbar.set_description(f"Processing daily {file.name:>54}")
        dataset.vstack(_read(file, filters.pyarrow_filters_daily), in_place=True)

    dataset.rechunk()

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

    # Round-about way to force timezone in there
    # https://github.com/pola-rs/polars/issues/12761
    tz_exprs_start = [
        polars.when(polars.col("Timezone") == tz).then(
            polars.col("Start").dt.replace_time_zone(tz).dt.convert_time_zone("UTC")
        )
        for tz in metadata["Timezone"].unique()
    ]
    tz_exprs_end = [
        polars.when(polars.col("Timezone") == tz).then(
            polars.col("End").dt.replace_time_zone(tz).dt.convert_time_zone("UTC")
        )
        for tz in metadata["Timezone"].unique()
    ]

    joined = (
        dataset.join(metadata, left_on="Samplingpoint", right_on="selector", how="left")
        .with_columns(
            polars.coalesce(tz_exprs_start),
            polars.coalesce(tz_exprs_end),
        )
        .drop("Timezone")
    )

    return joined


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
        dataframe, metadata = self._read(varname)
        dataframe = dataframe.with_columns(
            polars.col("Samplingpoint").str.replace("/", "_").alias("station")
        )
        return EEAData(dataframe, varname, metadata)

    def _read(
        self,
        variable: str,
    ) -> tuple[polars.DataFrame, ...]:
        filters = _transform_filters(self._get_filters())

        # TODO: Enable depending on data wanted from e.g. time requested
        dataset = polars.DataFrame(
            schema={
                "Samplingpoint": str,
                "Pollutant": polars.Int32,
                "Start": polars.Datetime("ns"),
                "End": polars.Datetime("ns"),
                "Value": polars.Float32,
                "Unit": str,
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

        hourly_dataset = _read_hourly_files(
            hourly_paths,
            self._stations,
            filters,
        )
        if len(daily_paths) == 0:
            dataset = hourly_dataset
        else:
            daily_dataset = _read_daily_files(
                daily_paths,
                self._stations,
                filters,
            )
            dataset = hourly_dataset.vstack(daily_dataset)

        return dataset, stations

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
