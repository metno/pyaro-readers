import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from collections.abc import Iterable
import importlib.resources
import dataclasses

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
    def __init__(self, data, variable: str) -> None:
        self._data = data
        self._variable = variable

    @property
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
        return EEAData(self._data.filter(index), self._variable)

    @property
    def values(self) -> np.ndarray:
        return np.array(self._data["Value"], dtype=float)

    @property
    def stations(self) -> np.ndarray:
        return np.array(self._data["station"])

    @property
    def latitudes(self) -> np.ndarray:
        return np.array(self._data["Latitude"], dtype=float)

    @property
    def longitudes(self) -> np.ndarray:
        return np.array(self._data["Longitude"], dtype=float)

    @property
    def altitudes(self) -> np.ndarray:
        return np.array(self._data["Altitude"], dtype=float)

    @property
    def start_times(self) -> np.ndarray:
        return np.array(self._data["Start"])

    @property
    def end_times(self) -> np.ndarray:
        return np.array(self._data["End"])

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
        return np.array(valid)

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
            "Pollutant",
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
    country: pyaro.timeseries.Filter.CountryFilter | None
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
    offset = timedelta(hours=26)

    return [
        ("Start", ">=", min_time - offset),
        ("Start", "<=", max_time + offset),
        ("End", ">=", min_time - offset),
        ("End", "<=", max_time + offset),
    ]


def _transform_filters(
    filters: Iterable[pyaro.timeseries.Filter.Filter], variable_id: int
) -> _Filters:
    pollutant_filter = ("Pollutant", "=", variable_id)
    validity_filter = ("Validity", ">", 0)

    pyarrow_filters_daily = [pollutant_filter, validity_filter]
    pyarrow_filters_hourly = pyarrow_filters_daily.copy()
    country_filter = None
    time_filter = None

    for filter in filters:
        if isinstance(filter, pyaro.timeseries.Filter.TimeBoundsFilter):
            if filter.has_envelope():
                pyarrow_filters_hourly.extend(_pyarrow_timefilter_hourly(filter))
                pyarrow_filters_daily.extend(_pyarrow_timefilter_daily(filter))
            time_filter = filter
        elif isinstance(filter, pyaro.timeseries.Filter.CountryFilter):
            country_filter = filter
        else:
            continue  # handled post-read

    return _Filters(
        pyarrow_filters_daily=pyarrow_filters_daily,
        pyarrow_filters_hourly=pyarrow_filters_hourly,
        country=country_filter,
        time=time_filter,
    )


def _read_hourly_files(
    datapaths: list[Path],
    variable: int,
    metadata: polars.DataFrame,
    filters: _Filters,
) -> polars.DataFrame:
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

    pbar = tqdm(datapaths, disable=None)
    for file in pbar:
        pbar.set_description(f"Processing hourly {file.name:>54}")
        dataset.vstack(_read(file, filters.pyarrow_filters_hourly), in_place=True)

    # Join with metadata table to get latitude, longitude and altitude
    metadata = metadata.with_columns(
        (
            polars.col("Country").map_elements(
                _country_code_eea, return_dtype=polars.String
            )
            + "/"
            + polars.col("Sampling Point Id")
        ).alias("selector"),
    ).select(
        [
            "selector",
            "Altitude",
            "Longitude",
            "Latitude",
            "Duration Unit",
            "Air Quality Station Area",
            "Air Quality Station Type",
        ]
    )

    # OBS: Times are given in this timezone for non-daily observations
    # this assumption is also used for pyarrow filtering
    original_timezone_for_hourly_data = "Etc/GMT+1"
    joined = (
        dataset.join(metadata, left_on="Samplingpoint", right_on="selector", how="left")
        .with_columns(
            polars.col("Samplingpoint").str.replace("/", "_"),
            polars.col("Start")
            .dt.replace_time_zone(original_timezone_for_hourly_data)
            .dt.convert_time_zone("UTC"),
            polars.col("End")
            .dt.replace_time_zone(original_timezone_for_hourly_data)
            .dt.convert_time_zone("UTC"),
        )
        .filter(
            polars.col("Duration Unit").ne("day"),  # Timezone assumption filter
        )
    )

    assert (
        joined.filter(polars.col("Longitude").is_null()).shape[0] == 0
    ), "Some stations does not have a suitable left join"

    return joined


def _read_daily_files(
    datapaths: list[Path],
    variable: int,
    metadata: polars.DataFrame,
    filters: _Filters,
) -> polars.DataFrame:
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

    pbar = tqdm(datapaths, disable=None)
    for file in pbar:
        pbar.set_description(f"Processing daily {file.name:>54}")
        dataset.vstack(_read(file, filters.pyarrow_filters_daily), in_place=True)

    # Join with metadata table to get latitude, longitude and altitude
    metadata = metadata.with_columns(
        (
            polars.col("Country").map_elements(
                _country_code_eea, return_dtype=polars.String
            )
            + "/"
            + polars.col("Sampling Point Id")
        ).alias("selector"),
    ).select(
        [
            "selector",
            "Altitude",
            "Longitude",
            "Latitude",
            "Duration Unit",
            "Air Quality Station Area",
            "Air Quality Station Type",
            "Timezone",
        ]
    )

    timezone_mapper = {
        "UTC-04": "Etc/GMT-4",
        "UTC-03": "Etc/GMT-3",
        "UTC": "UTC",
        "UTC+01": "Etc/GMT+1",
        "UTC+02": "Etc/GMT+2",
        "UTC+03": "Etc/GMT+3",
        "UTC+04": "Etc/GMT+4",
    }
    # Round-about way to force timezone in there
    # https://github.com/pola-rs/polars/issues/12761
    tz_exprs_start = [
        polars.when(polars.col("Timezone").str.to_uppercase() == tz).then(
            polars.col("Start")
            .dt.replace_time_zone(tz_valid)
            .dt.convert_time_zone("UTC")
        )
        for tz, tz_valid in timezone_mapper.items()
    ]
    tz_exprs_end = [
        polars.when(polars.col("Timezone").str.to_uppercase() == tz).then(
            polars.col("End").dt.replace_time_zone(tz_valid).dt.convert_time_zone("UTC")
        )
        for tz, tz_valid in timezone_mapper.items()
    ]

    joined = (
        dataset.join(metadata, left_on="Samplingpoint", right_on="selector", how="left")
        .with_columns(
            polars.coalesce(tz_exprs_start),
            polars.coalesce(tz_exprs_end),
        )
        .drop("Timezone")
    )

    assert (
        joined.filter(polars.col("Longitude").is_null()).shape[0] == 0
    ), "Some stations does not have a suitable left join"

    return joined


class EEATimeseriesReader(AutoFilterReader):
    def __init__(
        self,
        filename_or_obj_or_url,
        filters=[],
        dataset: Literal["historical", "verified", "unverified"] = "unverified",
        station_area: str | list[str] = "all",
        station_type: str | list[str] = "all",
        metadata_file: str | None = None,
    ):
        self._set_filters(filters)
        data_directory = Path(filename_or_obj_or_url)
        if metadata_file is None:
            metadata_file = data_directory.joinpath("metadata.csv")
        self._metadata = polars.read_csv(
            metadata_file,
            schema_overrides={
                "Air Quality Station Nat Code": polars.String,
                "Detection Limit": polars.Float32,
            },
        )
        self._dataset = dataset

        # Vocabulary as found at https://dd.eionet.europa.eu/vocabulary/aq/pollutant
        pollutant_file = importlib.resources.files("pyaro_readers.eeareader").joinpath(
            "pollutant.csv"
        )
        self._metadata_pollutant = polars.read_csv(pollutant_file).with_columns(
            polars.col("URI")
            .str.strip_prefix("http://dd.eionet.europa.eu/vocabulary/aq/pollutant/")
            .cast(polars.Int32)
            .alias("Id"),
        )
        assert len(self._metadata_pollutant["Id"].unique()) == len(
            self._metadata_pollutant
        ), "Pollutants are not unique"

        self._data_directory = data_directory

        if isinstance(station_area, str):
            self._station_area = [station_area]
        else:
            self._station_area = station_area

        if isinstance(station_type, str):
            self._station_type = [station_type]
        else:
            self._station_type = station_type

    def metadata(self) -> dict[str, str]:
        metadata = dict()
        metadata["what"] = "EEA reader"
        metadata["download_url"] = "https://eeadmz1-downloads-webapp.azurewebsites.net/"
        return metadata

    def _unfiltered_data(self, varname: str) -> Data:
        dataframe = self._read(varname)
        dataframe = dataframe.with_columns(
            polars.col("Samplingpoint").str.replace("/", "_").alias("station")
        )
        return EEAData(dataframe, varname)

    def _read(
        self,
        variable: str | int,
    ) -> polars.DataFrame:
        # https://dd.eionet.europa.eu/vocabulary/aq/pollutant
        if isinstance(variable, int):
            variable_id = variable
        else:
            # Might be more than one, but we choose the first one
            pollutant_candidates = self._metadata_pollutant.filter(
                polars.col("Notation").eq(variable)
            )
            if len(pollutant_candidates) == 0:
                raise EEAReaderException(f"No variable ID found for {variable}")
            variable_id = pollutant_candidates["Id"][0]

        filters = _transform_filters(self._get_filters(), variable_id)
        historical_path = self._data_directory.joinpath("historical")
        verified_path = self._data_directory.joinpath("verified")
        unverified_path = self._data_directory.joinpath("unverified")

        # TODO: Enable depending on data wanted from e.g. time requested
        searchpaths = []
        if self._dataset == "historical":
            searchpaths.extend(historical_path)
        elif self._dataset == "verified":
            searchpaths.append(verified_path)
        elif self._dataset == "unverified":
            searchpaths.append(unverified_path)

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
        countries = _country_code_mappings_eea.values()

        paths: list[str, Path] = []
        for countrycode in countries:
            if filters.country is not None:
                # Reverse map EEA countrycode to ISO countrycode
                iso_countrycode = _country_code_eea_to_iso(countrycode)
                if not filters.country.has_country(iso_countrycode):
                    continue

            for searchpath in searchpaths:
                for freq in ["hourly", "daily"]:
                    spath = searchpath.joinpath(freq)
                    if not spath.exists():
                        continue
                    unknown_ccs = set(i.name for i in spath.iterdir()) - set(countries)
                    for dir in unknown_ccs:
                        logger.info(
                            f"Directory {dir} is ignored (not matching any country code)"
                        )
                    countrypath = spath.joinpath(countrycode)
                    if not countrypath.exists():
                        continue
                    countrypaths = countrypath.rglob("*.parquet")
                    # Filter based on station metadata
                    if self._dataset == "historical":
                        # For historical data we don't have any consistency checks and skip
                        # this check
                        pass
                    else:
                        # For efficiency we check the filename against the metadata
                        # to filter out any species we are not interested in
                        countrypaths = filter_filenames_based_on_metadata(
                            self._metadata, countrypaths, variable
                        )
                    paths.extend(
                        sorted([(freq, c) for c in countrypaths], key=lambda x: x[1])
                    )

        hourly_paths = [p[1] for p in paths if p[0] == "hourly"]
        hourly_dataset = _read_hourly_files(
            hourly_paths,
            variable_id,
            self._metadata,
            filters,
        )
        daily_paths = [p[1] for p in paths if p[0] == "daily"]
        if len(daily_paths) == 0:
            dataset = hourly_dataset
        else:
            daily_dataset = _read_daily_files(
                daily_paths,
                variable_id,
                self._metadata,
                filters,
            )
            dataset = hourly_dataset.vstack(daily_dataset)

        extra_filters = []
        if self._station_area != ["all"]:
            extra_filters.append(
                polars.col("Air Quality Station Area").is_in(self._station_area)
            )
        if self._station_type != ["all"]:
            extra_filters.append(
                polars.col("Air Quality Station Type").is_in(self._station_type)
            )

        if len(extra_filters) != 0:
            dataset = dataset.filter(*extra_filters)

        return dataset

    def _unfiltered_variables(self) -> list[str]:
        # Todo: Filtering might affect available variables
        pollutants = self._metadata["Air Pollutant"].unique()
        pollutants_metadata = self._metadata_pollutant["Notation"].unique()

        common = set(pollutants).intersection(pollutants_metadata)
        return list(sorted(common))

    def _unfiltered_stations(self) -> dict[str, Station]:
        stations = self._metadata.with_columns(
            (
                (
                    polars.col("Country").map_elements(
                        _country_code_eea,
                        return_dtype=polars.String,
                    )
                    + "/"
                    + polars.col("Sampling Point Id")
                )
                .str.replace("/", "_")
                .alias("station"),
                polars.col("Latitude").alias("latitude"),
                polars.col("Longitude").alias("longitude"),
                polars.col("Altitude").alias("altitude"),
                polars.col("Country")
                .map_elements(_country_code, return_dtype=polars.String)
                .alias("country"),
                polars.col("Source Data URL").alias("url"),
                (
                    polars.col("Country").map_elements(
                        _country_code_eea, return_dtype=polars.String
                    )
                    + "/"
                    + polars.col("Sampling Point Id")
                ).alias("long_name"),
                polars.col("Air Quality Station Area").alias("station_area"),
                polars.col("Air Quality Station Type").alias("station_type"),
            )
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
            ]
        )
        station_dicts = {s["station"]: Station(s) for s in stations.to_dicts()}
        return station_dicts

    def close(self) -> None:
        pass


class EEATimeseriesEngine(AutoFilterEngine):
    def description(self) -> str:
        return """EEA reader for parquet files

Read and filter hourly data from EEA stations using the unverified dataset.

Files must be downloaded from https://eeadmz1-downloads-webapp.azurewebsites.net/ using the following directory structure:
datadir (this path should be passed to `open`)
  - metadata.csv (from https://discomap.eea.europa.eu/App/AQViewer/index.html?fqn=Airquality_Dissem.b2g.measurements)
  - historical (directory)
  - verified (directory)
  - unverified
    - hourly
      - AD
        - file1.parquet
        - file2.parquet
        - ...
      - AL
    - daily
      - ...
    - ...

In each category (historical, verified, unverified) the time frequency and then the EEA country codes are used.
EEA country codes might differ from pyaro country codes.

Data can be downloaded using the airbase tool (https://github.com/JohnPaton/airbase/)
OBS: Must use github version, pypi version does not download parquet files yet

airbase unverified --path datadir/unverified/hourly -p SO2 -p PM10 -p O3 -p NO2 -p CO -p NO -p PM2.5 -F hourly --metadata --overwrite
"""

    def url(self) -> str:
        return "https://github.com/metno/pyaro-readers"

    def reader_class(self) -> AutoFilterReader:
        return EEATimeseriesReader

    def open(self, filename, *args, **kwargs) -> Reader:
        return self.reader_class()(filename, *args, **kwargs)


# ISO 3166-1 alpha-2 for countries in EEA
_country_code_mappings: dict[str, str] = {
    "Albania": "AL",
    "Andorra": "AD",
    "Austria": "AT",
    "Belgium": "BE",
    "Bosnia and Herzegovina": "BA",
    "Bulgaria": "BG",
    "Croatia": "HR",
    "Cyprus": "CY",
    "Czechia": "CZ",
    "Denmark": "DK",
    "Estonia": "EE",
    "Finland": "FI",
    "France": "FR",
    "Georgia": "GE",
    "Germany": "DE",
    "Greece": "GR",
    "Hungary": "HU",
    "Iceland": "IS",
    "Ireland": "IE",
    "Italy": "IT",
    "Kosovo under UNSCR 1244/99": "XK",
    "Latvia": "LV",
    "Lithuania": "LT",
    "Luxembourg": "LU",
    "Malta": "MT",
    "Montenegro": "ME",
    "Netherlands": "NL",
    "North Macedonia": "MK",
    "Norway": "NO",
    "Poland": "PL",
    "Portugal": "PT",
    "Romania": "RO",
    "Serbia": "RS",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Spain": "ES",
    "Sweden": "SE",
    "Switzerland": "CH",
    "Türkiye": "TR",
    "Ukraine": "UA",
    "United Kingdom": "UK",
}


# ISO 3166-1 alpha-2 for countries in EEA
def _country_code(country: str) -> str | None:
    return _country_code_mappings.get(country)


# Country codes used in "Samplingpoint" provided by each country
_country_code_mappings_eea: dict[str, str] = _country_code_mappings.copy()
_country_code_mappings_eea.update(
    {
        "United Kingdom": "GB",
    }
)


def _country_code_eea_to_iso(country: str) -> str:
    if country == "GB":
        return "UK"
    return country


# Country codes used in "Samplingpoint" provided by each country
def _country_code_eea(country: str) -> str | None:
    return _country_code_mappings_eea.get(country)


def filter_filenames_based_on_metadata(
    metadata: polars.DataFrame, paths: Iterable[Path], varname: str
):
    """Filter out paths that do not correspond to the wanted variable.

    This function is based on an assumption of matching sampling point ID and metadata
    which is verified when downloading  # TODO: Document where
    """
    good_paths = []
    for path in paths:
        filename = path.stem
        matches = metadata.filter(
            polars.col("Sampling Point Id").str.replace(":", "_").eq(filename),
            polars.col("Air Pollutant").eq(varname),
        )
        if matches.is_empty():
            good_paths.append(path)
    return good_paths
