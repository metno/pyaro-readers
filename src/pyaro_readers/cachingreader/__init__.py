from typing import Any
import json
import hashlib
import pathlib
import os
import random

import pyaro
from pyaro.timeseries.AutoFilterReaderEngine import AutoFilterReader, AutoFilterEngine
from pyaro.timeseries import Reader, Data, Station
import polars
import polars.datatypes

from pyaro_readers.parquet import ParquetData


class CachingException(Exception):
    pass


def hash_object(obj: Any) -> str:
    to_be_hashed = json.dumps(obj).encode("utf8")
    m = hashlib.sha256()
    m.update(to_be_hashed)
    return m.hexdigest()


class CachingReader(AutoFilterReader):
    def __init__(
        self,
        dataset: dict[str, Any],
        cache_dir: str,
        cache_version: int = 0,
        *,
        filters,
    ):
        self._set_filters(filters)
        reader_id = dataset.pop("reader_id")
        filename = dataset.pop("filename_or_obj_or_url")

        self._reader = pyaro.open_timeseries(reader_id, filename, **dataset)
        self._cache_dir = pathlib.Path(cache_dir)
        try:
            self._cache_dir.mkdir(parents=True)
        except FileExistsError:
            pass

        # Creating a cache key which is unique to the dataset
        dataset_key = hash_object(dataset)[:8]
        # Embedding filenames directly leads to odd paths
        filename_key = hash_object(filename)[:8]
        self._common_cachekey = (
            f"{reader_id}-{filename_key}-{dataset_key}-{cache_version}"
        )

    def _unfiltered_data(self, varname: str) -> Data:
        # Check cache dir
        cachekey = f"{self._common_cachekey}-{varname}.pq"
        cachefile = self._cache_dir / cachekey
        try:
            ds = polars.read_parquet(cachefile)
            return ParquetData(ds, varname)
        except FileNotFoundError:
            pass

        data = self._reader.data(varname)
        ds = polars.DataFrame(
            {
                "variable": data.variable,
                "units": data.units,
                "value": data.values,
                "station": data.stations,
                "longitude": data.longitudes,
                "latitude": data.latitudes,
                "start_time": data.start_times.astype("datetime64[us]"),
                "end_time": data.end_times.astype("datetime64[us]"),
                "flag": data.flags,
                "altitude": data.altitudes,
                "standard_deviation": data.standard_deviations,
            },
            schema={
                "variable": str,
                "units": str,
                "value": float,
                "station": str,
                "longitude": float,
                "latitude": float,
                "start_time": polars.datatypes.Datetime(),
                "end_time": polars.datatypes.Datetime(),
                "flag": int,
                "altitude": float,
                "standard_deviation": float,
            },
        )

        randkey = random.randint(10000, 99999)
        tmpfile = self._cache_dir / f"{cachekey}.{randkey}.tmp"
        ds.write_parquet(
            tmpfile, compression="zstd", compression_level=7, statistics=False
        )
        os.rename(tmpfile, cachefile)
        return ParquetData(ds, varname)

    def _unfiltered_stations(self) -> dict[str, Station]:
        cachekey = f"{self._common_cachekey}-stations.json"
        cachefile = self._cache_dir / cachekey
        try:
            with cachefile.open("rb") as f:
                stations = json.load(f)
            return {k: Station(**v) for k, v in stations.items()}
        except FileNotFoundError:
            pass

        stations = self._reader.stations()
        randkey = random.randint(10000, 99999)
        tmpfile = self._cache_dir / f"{cachekey}.{randkey}.tmp"
        with tmpfile.open("w") as f:
            stations_serialisable = {k: v.init_kwargs() for k, v in stations.items()}
            json.dump(stations_serialisable, f)
        os.rename(tmpfile, cachefile)
        return stations

    def _unfiltered_variables(self) -> list[str]:
        cachekey = f"{self._common_cachekey}-variables.json"
        cachefile = self._cache_dir / cachekey

        try:
            with cachefile.open("rb") as f:
                return json.load(f)
        except FileNotFoundError:
            pass

        variables = self._reader.variables()
        randkey = random.randint(10000, 99999)
        tmpfile = self._cache_dir / f"{cachekey}.{randkey}.tmp"
        with tmpfile.open("w") as f:
            json.dump(variables, f)
        os.rename(tmpfile, cachefile)
        return variables

    def close(self):
        self._reader.close()


class CachingEngine(AutoFilterEngine):
    def description(self) -> str:
        return """Caching reader
        """

    def url(self) -> str:
        return "https://github.com/metno/pyaro-readers"

    def reader_class(self) -> Reader:
        return CachingReader
