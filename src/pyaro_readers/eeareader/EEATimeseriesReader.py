import logging
from os import path
from datetime import datetime, timedelta
import sys
from pathlib import Path
from typing import Tuple, Any
from collections.abc import Iterable
import functools
import importlib.resources
import dataclasses

from tqdm import tqdm
import numpy as np
import polars
from pyaro.timeseries import (
    AutoFilterReaderEngine,
    Data,
    NpStructuredData,
    Station,
    Reader,
)
import pyaro.timeseries

if sys.version_info >= (3, 11):  # pragma: no cover
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


logger = logging.getLogger(__name__)

FLAGS_VALID = {-99: False, -1: False, 1: True, 2: False, 3: False, 4: True}
VERIFIED_LVL = [1, 2, 3]
DATA_TOML = path.join(path.dirname(__file__), "data.toml")
FILL_COUNTRY_FLAG = False

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

TS_TYPE_DIFFS = {
    "daily": np.timedelta64(12, "h"),
    "instantaneous": np.timedelta64(0, "s"),
    "points": np.timedelta64(0, "s"),
    "monthly": np.timedelta64(15, "D"),
}


DTYPES = [
    ("values", "f"),
    ("stations", "U64"),
    ("latitudes", "f"),
    ("longitudes", "f"),
    ("altitudes", "f"),
    ("start_times", "datetime64[s]"),
    ("end_times", "datetime64[s]"),
    ("flags", "i2"),
    ("standard_deviations", "f"),
]


PARQUET_FIELDS = dict(
    values="Value",
    start_times="Start",
    end_times="End",
    flags="Validity",
)

METADATA_FILEDS = dict(
    stations="stationcode",
    latitudes="lat",
    longitudes="lon",
    altitudes="alt",
)


class EEATimeseriesReader(AutoFilterReaderEngine.AutoFilterReader):
    def __init__(
        self,
        filename,
        filters={},
    ):
        self._filename = filename
        self._stations = {}
        self._data = {}  # var -> {data-array}
        self._set_filters(filters)

        self.metadata = self._read_metadata(filename)
        self.data_cfg = self._read_cfg()

        self._read_polars(filters, filename)

    def _read_polars(self, filters, filename) -> None:
        try:
            species = filters["variables"]["include"]
        except Exception:
            species = []

        filter_time = False
        if "time_bounds" in filters:
            if "start_include" in filters["time_bounds"]:
                start_date = datetime.strptime(
                    filters["time_bounds"]["start_include"][0][0], TIME_FORMAT
                )
                end_date = datetime.strptime(
                    filters["time_bounds"]["start_include"][0][1], TIME_FORMAT
                )
                filter_time = True

        if len(species) == 0:
            raise ValueError(
                "As of now, you have to give the species you want to read in filter.variables.include"
            )

        filename = Path(filename)
        if not filename.is_dir():
            raise ValueError(
                "The filename must be an existing path where the data is found in folders with the country code as name"
            )
        for s in species:
            files = self._create_file_list(filename, s)
            if len(files) == 0:
                raise ValueError(f"could now find any files in {filename} for {s}")

            if filter_time:
                datapoints = (
                    self._filter_dates(
                        polars.scan_parquet(files), (start_date, end_date)
                    )
                    .select(polars.len())
                    .collect()[0, 0]
                )
            else:
                datapoints = (
                    polars.scan_parquet(files).select(polars.len()).collect()[0, 0]
                )

            array = np.empty(datapoints, np.dtype(DTYPES))

            data = None
            species_unit = None

            current_idx = 0

            for file in tqdm(files, disable=None):
                # Filters by time
                if filter_time:
                    lf = self._filter_dates(
                        polars.read_parquet(file), (start_date, end_date)
                    )
                    if lf.is_empty():
                        logger.info(f"Data for file {file} is empty. Skipping")
                        continue
                else:
                    lf = polars.read_parquet(file)

                # Filters out invalid data
                lf = lf.filter(polars.col(PARQUET_FIELDS["flags"]) > 0)

                # Changes timezones
                lf = lf.with_columns(
                    polars.col(PARQUET_FIELDS["start_times"])
                    .dt.replace_time_zone("Etc/GMT-1")
                    .dt.convert_time_zone("UTC")
                    .alias(PARQUET_FIELDS["start_times"])
                )

                lf = lf.with_columns(
                    polars.col(PARQUET_FIELDS["end_times"])
                    .dt.replace_time_zone("Etc/GMT-1")
                    .dt.convert_time_zone("UTC")
                    .alias(PARQUET_FIELDS["end_times"])
                )

                file_datapoints = lf.select(polars.len())[0, 0]

                if file_datapoints == 0:
                    continue
                df = lf
                try:
                    station_metadata = self.metadata[df.row(0)[0].split("/")[-1]]
                except Exception:
                    logger.info(
                        f'Could not extract the metadata for {df.row(0)[0].split("/")[-1]}'
                    )
                    continue

                file_unit = self._convert_unit(df.row(0)[df.get_column_index("Unit")])

                for key in PARQUET_FIELDS:
                    array[key][
                        current_idx : current_idx + file_datapoints
                    ] = df.get_column(PARQUET_FIELDS[key]).to_numpy()

                for key, value in METADATA_FILEDS.items():
                    array[key][
                        current_idx : current_idx + file_datapoints
                    ] = station_metadata[value]

                current_idx += file_datapoints

                if species_unit is None:
                    species_unit = file_unit
                else:
                    if species_unit != file_unit:
                        raise ValueError(
                            f"Found multiple units ({file_unit} and {species_unit}) for same species {s}"
                        )

                station_fields = {
                    "station": station_metadata[METADATA_FILEDS["stations"]],
                    "longitude": station_metadata[METADATA_FILEDS["longitudes"]],
                    "latitude": station_metadata[METADATA_FILEDS["latitudes"]],
                    "altitude": station_metadata[METADATA_FILEDS["altitudes"]],
                    "country": station_metadata["country"],
                    "url": "",
                    "long_name": station_metadata[METADATA_FILEDS["stations"]],
                }
                self._stations[station_metadata[METADATA_FILEDS["stations"]]] = Station(
                    station_fields
                )

            data = NpStructuredData(variable=s, units=species_unit)
            data.set_data(variable=s, units=species_unit, data=array)
            self._data[s] = data

    def _create_file_list(self, root: Path, species: str):
        results = [f for f in (root / species).glob("**/*.parquet")]
        return results

    def _filter_dates(
        self, lf: polars.LazyFrame | polars.DataFrame, dates: tuple[datetime]
    ) -> polars.LazyFrame | polars.DataFrame:
        if dates[0] >= dates[1]:
            raise ValueError(
                f"Error when filtering data. Last date {dates[1]} must be larger than the first {dates[0]}"
            )

        return lf.filter(
            polars.col(PARQUET_FIELDS["start_times"]).is_between(
                dates[0] + timedelta(hours=1), dates[1] + timedelta(hours=1)
            )
        )

    def _read_metadata(self, folder: str) -> dict:
        metadata = {}
        filename = Path(folder) / "metadata.csv"
        if not filename.exists():
            raise FileExistsError(f"Metadata file could not be found in {folder}")
        with filename.open("r") as f:
            f.readline()
            for line in f:
                words = line.split(", ")
                try:
                    lon = float(words[3])
                    lat = float(words[4])
                    alt = float(words[5])
                except Exception:
                    logger.info(
                        f"Could not interpret lat, lon, alt for line {line} in metadata. Skipping"
                    )
                    continue
                metadata[words[0]] = {
                    "lon": lon,
                    "lat": lat,
                    "alt": alt,
                    "stationcode": words[2],
                    "country": words[1],
                }

        return metadata

    def _read_cfg(self) -> dict:
        with open(DATA_TOML, "rb") as f:
            cfg = tomllib.load(f)
        return cfg

    def _convert_unit(self, unit: str) -> str:
        return self.data_cfg["units"][unit]

    def _unfiltered_data(self, varname) -> Data:
        return self._data[varname]

    def _unfiltered_stations(self) -> dict[str, Station]:
        return self._stations

    def _unfiltered_variables(self) -> list[str]:
        return list(self._data.keys())

    def close(self):
        pass


class EEATimeseriesEngine(AutoFilterReaderEngine.AutoFilterEngine):
    def reader_class(self):
        return EEATimeseriesReader

    def open(self, filename, *args, **kwargs) -> EEATimeseriesReader:
        return self.reader_class()(filename, *args, **kwargs)

    def description(self):
        return "Reader for new EEA data API using the pyaro infrastructure."

    def url(self):
        return "https://github.com/metno/pyaro-readers"


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
        return EEAData(self._data[index], self._variable)

    @property
    def values(self) -> np.ndarray:
        return np.array(self._data["Value"], dtype=float)

    @property
    def stations(self) -> np.ndarray:
        return np.array(self._data["Samplingpoint"], dtype=float)

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
    # TODO: Timezone fixup??
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
class _Filters():
    pyarrow: list[list[Any]]
    country: pyaro.timeseries.Filter.CountryFilter | None


def _transform_filters(filters: Iterable[pyaro.timeseries.Filter], variable_id: int) -> _Filters:
    pollutant_filter = ("Pollutant", "=", variable_id)
    validity_filter = ("Validity", "=", 1)

    pyarrow_filters = [pollutant_filter, validity_filter]
    country_filter = None

    for filter in filters:
        if isinstance(filter, pyaro.timeseries.Filter.TimeBoundsFilter):
            args = filter.init_kwargs()
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

    # if country_filter is None:
    #     country_filter = pyaro.timeseries.CountryFilter(exclude=None)
    return _Filters(pyarrow_filters, country_filter)


class EEATimeSeriesReader2(Reader):
    def __init__(
        self, filename_or_obj_or_url, filters=None, enable_progressbar: bool = False
    ):
        data_directory = Path(filename_or_obj_or_url)
        metadata_file = data_directory.joinpath("metadata.csv")
        self._metadata = polars.read_csv(metadata_file)

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
                if filter.name() in self.supported_filters():
                    self._filters.append(filter)
                else:
                    raise NotImplementedError(
                        f"This reader does not support filter {filter.name()}"
                    )
        self._data_directory = data_directory
        self._progressbar_enabled = enable_progressbar

    def supported_filters(self) -> list[str]:
        # TODO: support more filters
        return [
            # "variables",
            "time_bounds",
            # time_resolution,
            "stations",
            "countries",
            # flags,
            # altitude,
        ]

    def metadata(self) -> dict[str, str]:
        metadata = dict()
        metadata["what"] = "EEA reader"
        metadata["download_url"] = "https://eeadmz1-downloads-webapp.azurewebsites.net/"
        return metadata

    def data(self, varname: str) -> Data:
        data = self._read(varname)
        return EEAData(data, varname)

    def _read(
        self,
        variable: str,
    ) -> polars.DataFrame:
        # https://dd.eionet.europa.eu/vocabulary/aq/pollutant
        pollutant_candidates = self._metadata_pollutant.filter(
            polars.col("Notation").eq(variable)
        )
        if len(pollutant_candidates) == 0:
            raise Exception(f"No variable ID found for {variable}")

        # Might be more than one, but we choose the first one
        variable_id = pollutant_candidates["Id"][0]

        # historical_path = self._data_directory.joinpath("historical")
        # verified_path = self._data_directory.joinpath("verified")
        unverified_path = self._data_directory.joinpath("unverified")

        # TODO: Enable depending on data wanted from e.g. time requested
        searchpaths = [unverified_path]

        filters = _transform_filters(self._filters, variable_id)

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

        # assert set(i.name for i in unverified_path.iterdir()).issubset(
        #     countries
        # ), "Some directories has an unknown country code"

        paths = []
        for countrycode in countries:
            if filters.country is not None:
                # Reverse map EEA countrycode to ISO countrycode
                iso_countrycode = _country_code_eea_to_iso(countrycode)
                if not filters.country.has_country(iso_countrycode):
                    continue

            for searchpath in searchpaths:
                countrypath = searchpath.joinpath(countrycode)
                if not countrypath.exists():
                    continue
                countrypaths = countrypath.iterdir()
                paths.extend(sorted(countrypaths))

        pbar = tqdm(paths, disable=not self._progressbar_enabled)
        for file in pbar:
            pbar.set_description(f"Processing {file.name:>34}")

            dataset.vstack(_read(file, filters.pyarrow))

        dataset = dataset.rechunk()

        # Join with metadata table to get latitude, longitude and altitude
        metadata = self._metadata.with_columns(
            (
                polars.col("Country").map_elements(
                    _country_code_eea, return_dtype=str
                )
                + "/"
                + polars.col("Sampling Point Id")
            ).alias("selector")
        ).select(
            [
                "selector",
                "Altitude",
                "Longitude",
                "Latitude",
            ]
        )

        joined = dataset.join(
            metadata, left_on="Samplingpoint", right_on="selector", how="left"
        )
        assert (
            joined.filter(polars.col("Longitude").is_null()).shape[0] == 0
        ), "Some stations does not have a suitable left join"

        return joined

    def variables(self) -> list[str]:
        # Todo: Filtering might affect available variables
        pollutants = self._metadata["Air Pollutant"].unique()
        pollutants_metadata = self._metadata_pollutant["Notation"].unique()

        common = set(pollutants).intersection(pollutants_metadata)
        return list(sorted(common))

    def stations(self) -> list[str]:
        stations = self._metadata.with_columns(
            (
                polars.col("Country").map_elements(
                    _country_code_eea, return_dtype=str
                )
                + "/"
                + polars.col("Sampling Point Id")
            ).alias("selector")
        )["selector"]
        return list(stations)

    def close(self) -> None:
        pass


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
