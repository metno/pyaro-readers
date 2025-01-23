from typing import Literal, Any

import numpy as np
import cf_units
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


class MergingReaderException(Exception):
    pass


class MergingReaderConcatData(Data):
    def __init__(self, data: list[Data], variable: str) -> None:
        if len(data) == 0:
            raise MergingReaderException("Requires at least one dataset")
        self._data = data
        self._variable = variable

    @property
    def units(self) -> str:
        base_unit = self._data[0].units
        unit = cf_units.Unit(base_unit)
        for d in self._data[1:]:
            if unit.convert_to(1, d.units) != 1.0:
                raise MergingReaderException(
                    f"The units are not the same in all the datasets {base_unit} {d.units}"
                )
        return base_unit

    def keys(self):
        raise NotImplementedError

    def slice(self, index):
        return MergingReaderConcatData([d[index] for d in self._data], self._variable)

    @property
    def values(self) -> np.ndarray:
        return np.concatenate([d.values for d in self._data])

    @property
    def stations(self) -> np.ndarray:
        return np.concatenate([d.stations for d in self._data])

    @property
    def latitudes(self) -> np.ndarray:
        return np.concatenate([d.latitudes for d in self._data])

    @property
    def longitudes(self) -> np.ndarray:
        return np.concatenate([d.longitudes for d in self._data])

    @property
    def altitudes(self) -> np.ndarray:
        return np.concatenate([d.altitudes for d in self._data])

    @property
    def start_times(self) -> np.ndarray:
        return np.concatenate([d.start_times for d in self._data])

    @property
    def end_times(self) -> np.ndarray:
        return np.concatenate([d.end_times for d in self._data])

    @property
    def flags(self) -> np.ndarray:
        return np.concatenate([d.flags for d in self._data])

    @property
    def standard_deviations(self) -> np.ndarray:
        return np.concatenate([d.standard_deviations for d in self._data])

    def __len__(self) -> int:
        return sum(len(d) for d in self._data)


class MergingReader(AutoFilterReader):
    def __init__(
        self, datasets: list[dict[str, Any]], mode: Literal["concat"], filters=[]
    ):
        if mode != "concat":
            raise MergingReaderException(
                'Only merging mode "concat" is supported as of now'
            )
        self._mode = mode
        self._datasets = []
        self._set_filters(filters)
        for d in datasets:
            readername = d.pop("readername")
            self._datasets.append(
                pyaro.open_timeseries(readername, **d, filters=self._get_filters())
            )

    def _unfiltered_data(self, varname: str) -> Data:
        return MergingReaderConcatData(
            [d.data(varname) for d in self._datasets], varname
        )

    def _unfiltered_stations(self) -> list[str]:
        stations = []
        for d in self._datasets:
            stations.extend(d.stations())
        return stations

    def _unfiltered_variables(self) -> list[str]:
        variables = []
        for d in self._datasets:
            variables.extend(d.variables())
        return variables

    def close(self):
        for d in self._datasets:
            d.close()


class MergingReaderEngine(AutoFilterEngine):
    def description(self) -> str:
        return """Merge multiple datasets by concatenation of pyaro datasets
        """

    def url(self) -> str:
        return "https://github.com/metno/pyaro-readers"

    def reader_class(self) -> AutoFilterReader:
        return MergingReader
