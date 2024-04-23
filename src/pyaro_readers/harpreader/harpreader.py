import glob
import inspect
from pyaro.timeseries import (
    AutoFilterReaderEngine,
    Station,
    Data,
    NpStructuredData,
    Flag,
)
import logging
import os
import xarray as xr
import numpy as np
from collections import namedtuple
import re
import cfunits
import pyaro

logger = logging.getLogger(__name__)


class HARPReaderException(Exception):
    pass


class AeronetHARPReader(AutoFilterReaderEngine.AutoFilterReader):
    """
    Reader for netCDF files which follow the HARP convention.
    """

    def __init__(self, file: str):
        self._filters = []
        if os.path.isfile(file):
            self._file = file
        else:
            raise HARPReaderException(f"No such file: {file}")

        with xr.open_dataset(self._file) as harp:
            if harp.attrs.get("Conventions", None) != "HARP-1.0":
                raise ValueError(f"File is not a HARP file.")

        self._variables = self._read_file_variables()

    def _unfiltered_stations(self) -> dict[str, Station]:
        pass

    def close(self):
        pass

    def _read_file_variables(self) -> dict[str, str]:
        """Returns a mapping of variable name to unit for the dataset.

        Returns:
        --------
        dict[str, str] :
            A dictionary mapping variable name to its corresponding unit.

        """
        variables = {}
        with xr.open_dataset(self._file, decode_cf=False) as d:
            for vname, var in d.data_vars.items():
                variables[vname] = cfunits.Units(var.attrs["units"])

        return variables

    def _unfiltered_data(self, varname: str) -> NpStructuredData:
        """Returns unfiltered data for a variable.

        Parameters:
        -----------
        varname : str
            The variable name for which to return the data.

        Returns:
        --------
        NpStructuredArray
            The data.

        """

        units = self._variables[varname]
        data = NpStructuredData(varname, units)

        pattern = ""
        if os.path.isdir(self._file):
            pattern = os.path.join(self._file, "*.nc")
        else:
            pattern = self._file

        for f in glob.glob(pattern):
            self._get_data_from_single_file(f, varname, data)

        return data

    def _get_data_from_single_file(
        self, file: str, varname: str, data: NpStructuredData
    ) -> None:
        """Loads data for a variable from a single file.

        Parameters:
        -----------
        file : str
            The file path.
        varname : str
            The variable name.
        data : NpStructuredData
            Data instance to which the data will be appended to in-place.

        """
        dt = xr.open_dataset(file)

        values = dt[varname].to_numpy()

        values_length = len(values)
        start_time = np.asarray(dt["datetime_start"])
        stop_time = np.asarray(dt["datetime_stop"])
        lat = np.asarray([dt["latitude"]] * values_length)
        long = np.asarray([dt["longitude"]] * values_length)
        station = np.asarray([np.nan] * values_length)
        altitude = np.asarray([dt["altitude"]] * values_length)

        flags = np.asarray([Flag.VALID] * values_length)
        data.append(
            value=values,
            station=station,
            latitude=lat,
            longitude=long,
            altitude=altitude,
            start_time=start_time,
            end_time=stop_time,
            # TODO: Currently assuming that all observations are valid.
            flag=flags,
            standard_deviation=np.asarray([np.nan] * values_length),
        )

    def _unfiltered_variables(self) -> list[str]:
        """Returns a list of the variable names.

        Returns:
        list[str]
            The list of variable names.
        """
        return list(self._variables.keys())

    def close(self):
        pass


class AeronetHARPEngine(AutoFilterReaderEngine.AutoFilterEngine):
    def reader_class(self):
        return AeronetHARPReader

    def open(self, filename: str, *args, **kwargs) -> AeronetHARPReader:
        return self.reader_class()(filename, *args, **kwargs)

    def description(self):
        return inspect.doc(self)

    def url(self):
        return "https://github.com/metno/pyaro-readers"
