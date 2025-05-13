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
from pyaro.timeseries.Filter import FilterFactory, FilterCollection


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
        base_unit = None
        for d in self._data:
            if len(d) == 0:
                continue
            if base_unit is None:
                base_unit = d.units
                continue

            unit = cf_units.Unit(base_unit)
            if unit.convert(1, d.units) != 1.0:
                raise MergingReaderException(
                    f"The units are not the same in all the datasets {base_unit} {d.units}"
                )
        if base_unit is None:
            # Fallback to units from first dataset even if it is empty
            base_unit = self._data[0].units
        return base_unit

    @property
    def variable(self) -> str:
        return self._variable

    def keys(self):
        raise NotImplementedError

    def slice(self, index):
        # Split the index for each part
        lengths = [len(d) for d in self._data]
        *indices, _leftover = np.split(index, np.cumsum(lengths))
        return MergingReaderConcatData(
            [d.slice(ind) for d, ind in zip(self._data, indices)], self._variable
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
                reader_filters = FilterCollection(filterlist=reader_filters)
                if isinstance(filters, dict):
                    filtlist = []
                    for name, kwargs in filters.items():
                        filtlist.append(FilterFactory().get(name, **kwargs))
                    reader_filters = filtlist
                filters = self._get_filters() + list(reader_filters)
            else:
                filters = self._get_filters()
            self._datasets.append(
                pyaro.open_timeseries(readerid, filename, **d, filters=filters)
            )

    def _unfiltered_data(self, varname: str) -> Data:
        raise MergingReaderException("This method should not be called")

    def data(self, varname: str) -> Data:
        # This method is deliberately overridden to prevent
        # double filtering of the data
        return MergingReaderConcatData(
            [d.data(varname) for d in self._datasets], varname
        )

    def _unfiltered_stations(self) -> dict[str, Station]:
        raise MergingReaderException("This method should not be called")

    def stations(self) -> dict[str, Station]:
        # This method is deliberately overridden to prevent
        # double filtering of the data
        stations = {}
        for d in self._datasets:
            stations |= d.stations()
        return stations

    def _unfiltered_variables(self) -> list[str]:
        raise MergingReaderException("This method should not be called")

    def variables(self) -> list[str]:
        # This method is deliberately overridden to prevent
        # double filtering of the data
        variables = []
        for d in self._datasets:
            variables.extend(d.variables())
        return variables

    def close(self) -> None:
        for d in self._datasets:
            d.close()

    def metadata(self) -> dict[str, str]:
        all_metadata = [d.metadata() for d in self._datasets]
        all_metadata_keys = set()
        for m in all_metadata:
            all_metadata_keys |= m.keys()

        metadata = dict()
        for key in sorted(all_metadata_keys):
            values = [m.get(key, "none") for m in all_metadata]
            if all((v == values[0] for v in values)):
                # All datasets report the same metadata
                metadata[key] = values[0]
            else:
                metadata[key] = "-".join(values)

        return metadata


class MergingReaderEngine(AutoFilterEngine):
    def description(self) -> str:
        return """Merge multiple datasets by concatenation of pyaro datasets
        """

    def url(self) -> str:
        return "https://github.com/metno/pyaro-readers"

    def reader_class(self) -> AutoFilterReader:
        return MergingReader
