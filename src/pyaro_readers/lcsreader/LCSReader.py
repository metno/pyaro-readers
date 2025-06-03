from typing import Literal
from tqdm import tqdm
from pathlib import Path
from datetime import datetime

from pyaro.timeseries.AutoFilterReaderEngine import AutoFilterReader, AutoFilterEngine
from pyaro.timeseries import Reader, Data, Station
import polars as pl
import numpy as np

from geocoder_reverse_natural_earth import (
    Geocoder_Reverse_NE,
)


class LCSReaderException(Exception):
    pass


class LCSData(Data):
    def __init__(self, dataset: pl.DataFrame, variable: str):
        self._variable = variable
        self._dataset = dataset

        self._len_dataset = len(self._dataset)

    def __len__(self) -> int:
        return self._len_dataset

    def slice(self, index):
        return LCSData(self._dataset.filter(index), self._variable)

    @property
    def altitudes(self):
        return np.zeros(self._len_dataset)

    @property
    def start_times(self):
        return self._dataset["start"].to_numpy()

    @property
    def end_times(self):
        return self._dataset["stop"].to_numpy()

    @property
    def quality(self):
        return self._dataset["quality"].to_numpy()

    @property
    def network(self):
        return self._dataset["network"].to_numpy()

    # @property
    # def qc(self):
    #     return self._dataset["qc"].to_numpy()

    def keys(self):
        return set(self._dataset.columns) - set(["units"])

    @property
    def latitudes(self):
        return self._dataset["lat"].to_numpy()

    @property
    def longitudes(self):
        return self._dataset["lon"].to_numpy()

    @property
    def stations(self):
        return self._dataset["station_name"].to_numpy()

    @property
    def values(self):
        return self._dataset["PM25"].to_numpy()

    @property
    def units(self):
        return "ug m-3"

    @property
    def standard_deviations(self):
        return np.zeros(self._len_dataset)

    @property
    def flags(self):
        return self._dataset["quality"].to_numpy()

    @property
    def variable(self) -> str:
        return self._variable


class LCSReader(AutoFilterReader):

    read_columns = [
        "start",
        "stop",
        "station_name",
        "lon",
        "lat",
        "PM25",
        "spread",
        # "qc",    # Might want to read this at a later point, to give users better control over quality
        "quality",
        "network",
    ]

    def __init__(
        self,
        filename: str,
        min_quality: int = 2,
        min_spread: int = 3,
        network: Literal["PA", "SC", "both"] = "both",
        *,
        filters,
    ):

        self._set_filters(filters)

        mod_time = Path(filename).stat().st_mtime
        mod_time = datetime.fromtimestamp(mod_time)
        self._revision = f"{mod_time:%Y-%m-%dT%H:%M:%S}"

        if network.lower() not in ["pa", "sc", "both"]:
            raise LCSReaderException(f"Network must be either PA, SC or both")

        if min_spread > 3 or min_spread < 1:
            raise LCSReaderException(f"min_spread must be in range [1,3]")

        if min_quality > 2 or min_quality < 0:
            raise LCSReaderException(f"min_spread must be in range [0,2]")

        dataset = pl.scan_parquet(filename).select(self.read_columns)

        if network != "both":
            dataset = dataset.filter(pl.col("network").eq(network))

        dataset = dataset.filter(pl.col("spread").ge(float(min_spread)))
        dataset = dataset.filter(pl.col("quality").ge(float(min_quality)))

        self._dataset = dataset.collect()

    def metadata(self) -> dict[str, str]:
        return {"revision": self._revision}

    def _unfiltered_data(self, varname: str) -> LCSData:
        return LCSData(self._dataset, "PM25")

    def _unfiltered_stations(self) -> dict[str, Station]:

        ds = self._dataset.group_by("station_name").first()

        gcd = Geocoder_Reverse_NE()

        stations = dict()
        pbar = tqdm(ds.rows(named=True), disable=None)
        for row in pbar:
            pbar.set_description(f"Processing station {row['station_name']:>54}")
            stations[row["station_name"]] = Station(
                {
                    "station": row["station_name"],
                    "longitude": row["lon"],
                    "latitude": row["lat"],
                    "altitude": 0,
                    "country": gcd.lookup_nearest(row["lat"], row["lon"])["ISO_A2_EH"],
                    "url": "",
                    "long_name": row["station_name"],
                },
            )
        return stations

    def _unfiltered_variables(self) -> list[str]:
        return ["PM25"]

    def close(self):
        pass


class LCSTimeseriesEngine(AutoFilterEngine):
    def description(self) -> str:
        return """LCS reader
        """

    def url(self) -> str:
        return "https://figshare.com/articles/dataset/_i_Harmonized_Standardized_and_Corrected_Crowd-Sourced_Low-Cost_Sensor_i_PM_sub_2_5_sub_i_Data_f_i_i_rom_i_i_Sensor_community_and_PurpleAir_Networks_i_i_Across_Europe_i_/27195720/1"

    def reader_class(self) -> Reader:
        return LCSReader
