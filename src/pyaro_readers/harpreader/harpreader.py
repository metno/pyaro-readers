import glob
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

logger = logging.getLogger(__name__)

HARP_CONVENTION_STRING = "HARP-1.0"
HARP_DATA_MODEL = "NETCDF4"

UnitsInformation = namedtuple("UnitsInformation", ["reference_datetime", "unit"])


def extract_unit_information(unit_str: str) -> UnitsInformation:
    """
    Extracts units of the form "days since 2000-01-01" which are part of the HARP convention.
    Returns a tuple with the reference date, and the base unit.

    Parameters:
    unit_str : str
        The unit string to be converted, eg. "days since 2000-01-01"

    Returns:
    --------
    tuple:
        A named tuple where reference_datetime is the reference date. And unit is the base unit (eg. days).

    Note:
    Currently only converts days, because that's the files used by pyaerocom. May break with more
    complicated date strings.

    Note:
    -----
    http://stcorp.github.io/harp/doc/html/conventions/datetime.html


    """

    if not re.match("^[a-z]+ since ", unit_str):
        raise ValueError(
            f"Unit string, {unit_str} could not be parsed. Pattern matching failed."
        )

    split = unit_str.split(" ")
    if not split[0] in ["days"]:
        raise ValueError(
            f"Unit string, {unit_str} could not be parsed. {split[0]} is not a recognized unit."
        )
    try:
        return UnitsInformation(np.datetime64(split[2]), split[0])
    except:
        raise ValueError(
            f"Unit string, {unit_str} could not be parsed. Date conversion failed."
        )


class HARPReaderException(Exception):
    pass


class AeronetHARPReader(AutoFilterReaderEngine.AutoFilterReader):
    def __init__(self, file: str):
        if os.path.isfile(file):
            self._file = file
        else:
            raise HARPReaderException(f"No such file: {file}")

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
                try:
                    variables[vname] = extract_unit_information(var.attrs["units"])
                except:
                    variables[vname] = var.attrs["units"]

        return variables

    def _unfiltered_data(self, varname: str) -> NpStructuredData:
        units = self._variables[varname]
        data = NpStructuredData(varname, units)

        dt = xr.open_dataset(self._file)

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
            # TODO: Don't assume all observations are valid, maybe (?)
            flag=flags,
            standard_deviation=np.asarray([np.nan] * values_length),
        )

        return data

    def _unfiltered_variables(self) -> list[str]:
        return list(self._variables.keys())

    def close(self):
        pass


class AeronetHARPEngine(AutoFilterReaderEngine.AutoFilterEngine):
    def reader_class(self):
        return AeronetHARPReader

    def open(self, filename: str, *args, **kwargs) -> AeronetHARPReader:
        return self.reader_class()(filename, *args, **kwargs)

    def description(self):
        "Simple reader of HARP-files using the pyaro infrastructure"

    def url(self):
        return "https://github.com/metno/pyaro-readers"


if __name__ == "__main__":
    FOLDER = "/lustre/storeB/project/aerocom/aerocom1/AEROCOM_OBSDATA/CNEMC/aggregated/"
    r = AeronetHARPReader(f"{FOLDER}sinca-surface-157-999999-001.nc")

    print(r._variables)
    print(r._unfiltered_data("PM10_density"))
