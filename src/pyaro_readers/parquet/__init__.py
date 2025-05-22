from pyaro.timeseries.AutoFilterReaderEngine import AutoFilterReader, AutoFilterEngine
from pyaro.timeseries import Reader, Data, Station
import polars
import numpy as np


class ParquetReaderException(Exception):
    pass


class ParquetData(Data):
    def __init__(self, dataset: polars.DataFrame, variable: str):
        self._variable = variable
        self._dataset = dataset

    def __len__(self) -> int:
        return len(self._dataset)

    def slice(self, index):
        return ParquetData(self._dataset[index], self._variable)

    @property
    def variable(self) -> str:
        return self._variable

    @property
    def altitudes(self):
        return self._dataset["altitude"].to_numpy()

    @property
    def start_times(self):
        return self._dataset["start_time"].to_numpy()

    @property
    def end_times(self):
        return self._dataset["end_time"].to_numpy()

    @property
    def flags(self):
        return self._dataset["flag"].to_numpy()

    def keys(self):
        return set(self._dataset.columns) - set(["variable", "units"])

    @property
    def latitudes(self):
        return self._dataset["latitude"].to_numpy()

    @property
    def longitudes(self):
        return self._dataset["longitude"].to_numpy()

    @property
    def standard_deviations(self):
        return self._dataset["standard_deviation"].to_numpy()

    @property
    def stations(self):
        return self._dataset["station"].to_numpy()

    @property
    def values(self):
        return self._dataset["value"].to_numpy()

    @property
    def units(self):
        units = self._dataset["units"].unique()
        if len(units) > 1:
            raise ParquetReaderException(
                f"This dataset contains more than one unit: {units}"
            )
        return units[0]


class ParquetTimeseriesReader(AutoFilterReader):
    MANDATORY_COLUMNS = {
        "variable",
        "units",
        "value",
        "station",
        "longitude",
        "latitude",
        "start_time",
        "end_time",
    }
    OPTIONAL_COLUMNS_WITH_DEFAULTS = {
        "country": "",
        "flag": 0,
        "altitude": np.nan,
        "standard_deviation": np.nan,
    }

    def __init__(
        self,
        filename: str,
        station_metadata_fields: list[str] | None = None,
        *,
        filters,
    ):
        self._set_filters(filters)
        dataset = polars.read_parquet(filename)

        ds_cols = dataset.columns
        missing_mandatory = self.MANDATORY_COLUMNS - set(ds_cols)
        if len(missing_mandatory):
            raise ParquetReaderException(
                f"Expected the mandatory columns missing: {missing_mandatory}"
            )

        missing_optional = set(self.OPTIONAL_COLUMNS_WITH_DEFAULTS.keys()) - set(
            ds_cols
        )
        for missing in missing_optional:
            dataset = dataset.with_columns(
                polars.lit(self.OPTIONAL_COLUMNS_WITH_DEFAULTS[missing]).alias(missing)
            )

        self._dataset = dataset
        self._stationmetadatacols = (
            station_metadata_fields if station_metadata_fields is not None else []
        )

    def _unfiltered_data(self, varname: str) -> ParquetData:
        return ParquetData(
            self._dataset.filter(polars.col("variable").eq(varname)), varname
        )

    def _unfiltered_stations(self) -> dict[str, Station]:
        ds = self._dataset.group_by("station").first()

        stations = dict()
        for row in ds.rows(named=True):
            stations[row["station"]] = Station(
                {
                    "station": row["station"],
                    "longitude": row["longitude"],
                    "latitude": row["latitude"],
                    "altitude": row["altitude"],
                    "country": row["country"],
                    "url": "",
                    "long_name": row["station"],
                },
                metadata={m: row[m] for m in self._stationmetadatacols},
            )
        return stations

    def _unfiltered_variables(self) -> list[str]:
        return list(self._dataset["variable"].unique())

    def close(self):
        pass


class ParquetTimeseriesEngine(AutoFilterEngine):
    def description(self) -> str:
        return """Parquet reader
        """

    def url(self) -> str:
        return "https://github.com/metno/pyaro-readers"

    def reader_class(self) -> Reader:
        return ParquetTimeseriesReader
