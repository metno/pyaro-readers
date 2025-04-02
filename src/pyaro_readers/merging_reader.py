from typing import Literal, Any

import numpy as np
import cf_units
from pyaro.timeseries.AutoFilterReaderEngine import (
    AutoFilterReader,
    AutoFilterEngine,
)
from pyaro.timeseries import (
    Station,
    Data,
)
import pyaro.timeseries
from pyaro.timeseries.Filter import FilterFactory


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
            if unit.convert(1, d.units) != 1.0:
                raise MergingReaderException(
                    f"The units are not the same in all the datasets {base_unit} {d.units}"
                )
        return base_unit

    def keys(self):
        raise NotImplementedError

    def slice(self, index):
        # Split the index for each part
        lengths = [len(d) for d in self._data]
        *indices, _leftover = np.split(index, np.cumsum(lengths))
        return MergingReaderConcatData(
            [d[ind] for d, ind in zip(self._data, indices)], self._variable
        )

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
            readerid = d.pop("reader_id")
            filename = d.pop("filename_or_obj_or_url")
            if "filters" in d:
                reader_filters = d.pop("filters")
                if isinstance(filters, dict):
                    filtlist = []
                    for name, kwargs in filters.items():
                        filtlist.append(FilterFactory().get(name, **kwargs))
                    reader_filters = filtlist
                filters = self._get_filters() + reader_filters
            else:
                filters = self._get_filters()
            self._datasets.append(
                pyaro.open_timeseries(readerid, filename, **d, filters=filters)
            )

    def _unfiltered_data(self, varname: str) -> Data:
        return MergingReaderConcatData(
            [d.data(varname) for d in self._datasets], varname
        )

    def _unfiltered_stations(self) -> dict[str, Station]:
        stations = {}
        for d in self._datasets:
            stations |= d.stations()
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
