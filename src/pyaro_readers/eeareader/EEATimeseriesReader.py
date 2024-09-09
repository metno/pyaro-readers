from tqdm import tqdm
from datetime import datetime, timedelta

from geocoder_reverse_natural_earth import (
    Geocoder_Reverse_NE,
    Geocoder_Reverse_Exception,
)
import numpy as np
from pathlib import Path
import polars
from pyaro.timeseries import (
    AutoFilterReaderEngine,
    Data,
    Filter,
    Flag,
    NpStructuredData,
    Station,
)

FLAGS_VALID = {-99: False, -1: False, 1: True, 2: False, 3: False, 4: True}
VERIFIED_LVL = [1, 2, 3]
DATA_TOML = Path(__file__).parent / "data.toml"
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
        fill_country_flag: bool = FILL_COUNTRY_FLAG,
    ):
        self._filename = filename
        self._stations = {}
        self._data = {}  # var -> {data-array}
        self._set_filters(filters)

        self.metadata = self._read_metadata(filename)

        self._read_polars(filters, filename)

    def _read_polars(self, filters, filename) -> None:
        try:
            species = filters["variables"]["include"]
        except:
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
                f"As of now, you have to give the species you want to read in filter.variables.include"
            )

        filename = Path(filename)
        if not filename.is_dir():
            raise ValueError(
                f"The filename must be an existing path where the data is found in folders with the country code as name"
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

                station_metadata = self.metadata[df.row(0)[0].split("/")[-1]]

                file_unit = df.row(0)[df.get_column_index("Unit")]

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
        with open(filename, "r") as f:
            f.readline()
            for line in f:
                words = line.split(", ")
                try:
                    lon = float(words[3])
                    lat = float(words[4])
                    alt = float(words[5])
                except:
                    continue
                metadata[words[0]] = {
                    "lon": lon,
                    "lat": lat,
                    "alt": alt,
                    "stationcode": words[2],
                    "country": words[1],
                }

        return metadata

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
