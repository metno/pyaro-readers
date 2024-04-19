import glob
from pyaro.timeseries import AutoFilterReaderEngine, Station, Data, NpStructuredData
import logging
import os
import xarray as xr
import numpy as np

logger = logging.getLogger(__name__)

HARP_CONVENTION_STRING = "HARP-1.0"
HARP_DATA_MODEL = "NETCDF4"


class HARPReaderException(Exception):
    pass


class AeronetHARPReader(AutoFilterReaderEngine.AutoFilterReader):
    def __init__(self, file: str):
        if os.path.isfile(file):
            self._file = file
        else:
            raise HARPReaderException(f"No such file: {file}")

        self._variables = self._read_file_variables()

    def _unfiltered_data(self, varname: str) -> Data:
        pass

    def _unfiltered_stations(self) -> dict[str, Station]:
        pass

    def _unfiltered_variables(self) -> list[str]:
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
                # TODO: If necessary, translate variable names to pyaerocom, similar to what
                # is done in Ascii2NetcdfTimeseries.py
                # TODO: Translate units of the form 'days since 2000-01-01' (?)
                variables[vname] = var.attrs["units"]

        return variables

    def _unfiltered_data(self, varname: str) -> NpStructuredData:
        units = self._variables[varname]
        data = NpStructuredData(varname, units)

        dt = xr.open_dataset(self._file)

        values = dt[varname]

        values_length = len(values)
        # start_time = np.asarray([dt["datetime_start"]] * values_length)
        # stop_time = np.asarray([dt["datetime_stop"]] * values_length)
        # lat = np.asarray([dt["latitude"]] * values_length)
        # long = np.asarray([dt["longitude"]] * values_length)
        # station = np.nan
        # altitude = np.asarray([dt["altitude"]] * values_length)

        # data.append(
        #    value=values,
        #    station=station,
        #    latitude=lat,
        #    longitude=long,
        #    altitude=altitude,
        #    start_time=start_time,
        #    end_time=stop_time,
        # )

        start_time = dt["datetime_start"]
        stop_time = dt["datetime_stop"]
        lat = dt["latitude"]
        long = dt["longitude"]
        station = np.nan
        altitude = dt["altitude"]


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
    FOLDER = "/home/thlun8736/Documents/data/aggregated/"
    r = AeronetHARPReader(f"{FOLDER}sinca-surface-157-999999-001.nc")

    print(r._unfiltered_data("PM10_density"))
