import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from collections.abc import Iterable
import importlib.resources
import dataclasses

from tqdm import tqdm
import numpy as np
import polars
from pyaro.timeseries import (
    Data,
    Reader,
    Engine,
    Station,
)
import pyaro.timeseries


logger = logging.getLogger(__name__)


class EEAData(Data):
    def __init__(self, data, variable: str) -> None:
        self._data = data
        self._variable = variable

    @property
    def units(self) -> str:
        units = self._data["Unit"].unique()
        if len(units) != 1:
            raise Exception("Multiple different units present in this dataset")
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
        return np.array(self._data["Samplingpoint"])

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
    pyarrow: list[tuple[str, str, datetime]]
    country: pyaro.timeseries.Filter.CountryFilter | None
    time: pyaro.timeseries.Filter.TimeBoundsFilter | None


def _pyarrow_timefilter(
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


def _transform_filters(
    filters: Iterable[pyaro.timeseries.Filter], variable_id: int
) -> _Filters:
    pollutant_filter = ("Pollutant", "=", variable_id)
    validity_filter = ("Validity", "=", 1)

    pyarrow_filters = [pollutant_filter, validity_filter]
    country_filter = None
    time_filter = None

    for filter in filters:
        if isinstance(filter, pyaro.timeseries.Filter.TimeBoundsFilter):
            pyarrow_filters.extend(_pyarrow_timefilter(filter))
            time_filter = filter
        elif isinstance(filter, pyaro.timeseries.Filter.StationFilter):
            args = filter.init_kwargs()
            include = args["include"]
            exclude = args["exclude"]
            if len(include) > 0:
                pyarrow_filters.append(("Samplingpoint", "in", include))
            if len(exclude) > 0:
                pyarrow_filters.append(("Samplingpoint", "not in", exclude))
        elif isinstance(filter, pyaro.timeseries.Filter.CountryFilter):
            country_filter = filter
        else:
            raise NotImplementedError(f"Filter {filter.name()} not supported")

    return _Filters(pyarrow_filters, country=country_filter, time=time_filter)


@dataclasses.dataclass
class _DataFrame:
    frame: polars.DataFrame
    postfilter_time: pyaro.timeseries.Filter.TimeBoundsFilter | None


class EEATimeseriesReader(Reader):
    # TODO: support more filters
    supported_filters: list[str] = [
        # "variables",
        "time_bounds",
        # time_resolution,
        "stations",
        "countries",
        # flags,
        # altitude,
    ]

    def __init__(
        self, filename_or_obj_or_url, filters=None, enable_progressbar: bool = False
    ):
        data_directory = Path(filename_or_obj_or_url)
        metadata_file = data_directory.joinpath("metadata.csv")
        self._metadata = polars.read_csv(
            metadata_file,
            schema_overrides={
                "Air Quality Station Nat Code": str,
                "Detection Limit": float,
            },
        )

        # Vocabulary as found at https://dd.eionet.europa.eu/vocabulary/aq/pollutant
        pollutant_file_bytes = importlib.resources.files(
            "pyaro_readers.eeareader"
        ).joinpath("pollutant.csv")
        self._metadata_pollutant = polars.read_csv(pollutant_file_bytes).with_columns(
            polars.col("URI")
            .str.strip_prefix("http://dd.eionet.europa.eu/vocabulary/aq/pollutant/")
            .cast(polars.Int32)
            .alias("Id"),
        )
        assert len(self._metadata_pollutant["Id"].unique()) == len(
            self._metadata_pollutant
        ), "Pollutants are not unique"

        self._filters = []
        if filters is not None:
            for filter in filters:
                if filter.name() in self.supported_filters:
                    self._filters.append(filter)
                else:
                    raise NotImplementedError(
                        f"This reader does not support filter {filter.name()}"
                    )
        self._data_directory = data_directory
        self._progressbar_enabled = enable_progressbar

    def metadata(self) -> dict[str, str]:
        metadata = dict()
        metadata["what"] = "EEA reader"
        metadata["download_url"] = "https://eeadmz1-downloads-webapp.azurewebsites.net/"
        return metadata

    def data(self, varname: str) -> Data:
        dataframe = self._read(varname)
        if dataframe.postfilter_time is None:
            return EEAData(dataframe.frame, varname)
        else:
            stations = self.stations()
            data = dataframe.frame
            return dataframe.postfilter_time.filter_data(
                EEAData(data, varname), stations, varname
            )

    def _read(
        self,
        variable: str | int,
    ) -> _DataFrame:
        # https://dd.eionet.europa.eu/vocabulary/aq/pollutant
        if isinstance(variable, int):
            variable_id = variable
        else:
            # Might be more than one, but we choose the first one
            pollutant_candidates = self._metadata_pollutant.filter(
                polars.col("Notation").eq(variable)
            )
            if len(pollutant_candidates) == 0:
                raise Exception(f"No variable ID found for {variable}")
            variable_id = pollutant_candidates["Id"][0]

        filters = _transform_filters(self._filters, variable_id)

        # historical_path = self._data_directory.joinpath("historical")
        # verified_path = self._data_directory.joinpath("verified")
        unverified_path = self._data_directory.joinpath("unverified")

        # TODO: Enable depending on data wanted from e.g. time requested
        searchpaths = [unverified_path]

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

        paths = []
        for countrycode in countries:
            if filters.country is not None:
                # Reverse map EEA countrycode to ISO countrycode
                iso_countrycode = _country_code_eea_to_iso(countrycode)
                if not filters.country.has_country(iso_countrycode):
                    continue

            for searchpath in searchpaths:
                assert set(i.name for i in searchpath.iterdir()).issubset(
                    countries
                ), "Some directories has an unknown country code"
                countrypath = searchpath.joinpath(countrycode)
                if not countrypath.exists():
                    continue
                countrypaths = countrypath.iterdir()
                paths.extend(sorted(countrypaths))

        pbar = tqdm(paths, disable=not self._progressbar_enabled)
        for file in pbar:
            pbar.set_description(f"Processing {file.name:>34}")

            dataset.vstack(_read(file, filters.pyarrow), in_place=True)

        # Join with metadata table to get latitude, longitude and altitude
        metadata = self._metadata.with_columns(
            (
                polars.col("Country").map_elements(_country_code_eea, return_dtype=str)
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
            ]
        )

        # OBS: Times are given in this timezone for non-daily observations
        # this assumption is also used for pyarrow filtering
        original_timezone_for_hourly_data = "Etc/GMT+1"
        joined = (
            dataset.join(
                metadata, left_on="Samplingpoint", right_on="selector", how="left"
            )
            .with_columns(
                polars.col("Start")
                .dt.replace_time_zone(original_timezone_for_hourly_data)
                .dt.convert_time_zone("UTC"),
                polars.col("End")
                .dt.replace_time_zone(original_timezone_for_hourly_data)
                .dt.convert_time_zone("UTC"),
            )
            .filter(
                polars.col("Duration Unit").eq("hour"),
            )
        )

        assert (
            joined.filter(polars.col("Longitude").is_null()).shape[0] == 0
        ), "Some stations does not have a suitable left join"

        return _DataFrame(frame=joined, postfilter_time=filters.time)

    def variables(self) -> list[str]:
        # Todo: Filtering might affect available variables
        pollutants = self._metadata["Air Pollutant"].unique()
        pollutants_metadata = self._metadata_pollutant["Notation"].unique()

        common = set(pollutants).intersection(pollutants_metadata)
        return list(sorted(common))

    def stations(self) -> dict[str, Station]:
        stations = self._metadata.with_columns(
            (
                (
                    polars.col("Country").map_elements(
                        _country_code_eea, return_dtype=str
                    )
                    + "/"
                    + polars.col("Sampling Point Id")
                ).alias("station"),
                polars.col("Latitude").alias("latitude"),
                polars.col("Longitude").alias("longitude"),
                polars.col("Altitude").alias("altitude"),
                polars.col("Country")
                .map_elements(_country_code, return_dtype=str)
                .alias("country"),
                polars.col("Source Data URL").alias("url"),
                (
                    polars.col("Country").map_elements(
                        _country_code_eea, return_dtype=str
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


class EEATimeseriesEngine(Engine):
    args: list[str] = ["filename_or_obj_or_url", "enable_progressbar"]
    supported_filters: list[str] = EEATimeseriesReader.supported_filters
    description: str = """EEA reader for parquet files

Read and filter hourly data from EEA stations using the unverified dataset.

Files must be downloaded from https://eeadmz1-downloads-webapp.azurewebsites.net/ using the following directory structure:
datadir (this path should be passed to `open`)
  - metadata.csv (from https://discomap.eea.europa.eu/App/AQViewer/index.html?fqn=Airquality_Dissem.b2g.measurements)
  - historical (directory)
  - verified (directory)
  - unverified
    - AD
      - file1.parquet
      - file2.parquet
      - ...
    - AL
    - ...

In each category (historical, verified, unverified) the EEA country codes are used.
This might differ from pyaro country codes.

Data can be downloaded using the airbase tool (https://github.com/JohnPaton/airbase/)
OBS: Must use github version, pypi version does not download parquet files yet

airbase unverified --path datadir/unverified/ -p SO2 -p PM10 -p O3 -p NO2 -p CO -p NO -p PM2.5 -F hourly --metadata --overwrite
"""
    url: str = "https://github.com/metno/pyaro-readers"

    def open(
        self, filename_or_obj_or_url, enable_progressbar: bool = False, *, filters=None
    ):
        return EEATimeseriesReader(
            filename_or_obj_or_url,
            enable_progressbar=enable_progressbar,
            filters=filters,
        )


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
