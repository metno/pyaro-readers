import glob
from pyaro.timeseries import AutoFilterReaderEngine, Station, Data, NpStructuredData
import logging
import os
import xarray as xr

logger = logging.getLogger(__name__)

HARP_CONVENTION_STRING = "HARP-1.0"
HARP_DATA_MODEL = "NETCDF4"


class HARPReaderException(Exception):
    pass


class AeronetHARPReader(AutoFilterReaderEngine.AutoFilterReader):
    def __init__(self, directory: str):
        if os.path.isdir(directory):
            self._directory = directory
        else:
            raise HARPReaderException(f"No such directory: {directory}")

        self._files = []
        for file in glob.iglob(f"{FOLDER}*"):
            self._files.append(file)

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
        for f in self._files:
            logger.info(f"Processing {f}...")
            if not os.path.exists(f):
                logger.info(f"Data file {f}...")
                continue

            with xr.open_dataset(f, decode_cf=False) as d:
                # decode_cf ensures that xarray does not attempt to decode units according
                # to CF conventions.
                for vname, var in d.data_vars.items():
                    # TODO: If necessary, translate variable names to pyaerocom, similar to what
                    # is done in Ascii2NetcdfTimeseries.py
                    # TODO: Translate units of the form 'days since 2000-01-01' (?)

                    variables[vname] = var.attrs["units"]

        return variables


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
    print("Test")
    FOLDER = "/home/thlun8736/Documents/data/aggregated/"
    r = AeronetHARPReader(FOLDER)
