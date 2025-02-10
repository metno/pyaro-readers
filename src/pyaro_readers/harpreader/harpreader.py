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
from pathlib import Path
from tqdm import tqdm
import cf_units
from pyaro_readers.units_helpers import UALIASES
import datetime

logger = logging.getLogger(__name__)


class HARPReaderException(Exception):
    pass


class AeronetHARPReader(AutoFilterReaderEngine.AutoFilterReader):
    """
    Reader for netCDF files which follow the HARP convention.
    """

    FILE_MASK = "*.nc"
    COORD_NAMES = [
        "latitude",
        "longitude",
        "altitude",
        "datetime_start",
        "datetime_stop",
    ]

    def __init__(
        self,
        file: Path | str,
        filters=[],
        vars_to_read: list[str] = None,
    ):
        self._filters = filters
        realpath = Path(file).resolve()

        self._data = {}
        self._files = []
        self._stations = {}
        self._vars_to_read = vars_to_read
        self._set_filters(filters)

        # variable include filter comes like this
        # {'variables': {'include': ['PM10_density']}}
        # test for variable filter
        if "variables" in filters:
            if "include" in filters["variables"]:
                vars_to_read = filters["variables"]["include"]
                self._vars_to_read = vars_to_read
                logger.info(f"applying variable include filter {vars_to_read}...")

        if os.path.isfile(realpath) or os.path.isdir(realpath):
            pass
        else:
            raise HARPReaderException(f"No such file or directory: {file}")

        if os.path.isdir(file):
            pattern = os.path.join(file, self.FILE_MASK)
            self._files = glob.glob(pattern)
        else:
            self._files.append(file)

    def read(self):
        """reading method"""
        # check if the data has been read already
        if len(self._data) != 0:
            return
        bar = tqdm(total=len(self._files), disable=None)

        for f_idx, _file in enumerate(self._files):
            logger.info(f"Reading {_file}")
            bar.update(1)
            self._variables = self._read_file_variables(_file)
            # initialise all variables if not done yet
            for _var in self._variables:
                # skip coordinate names
                if _var in self.COORD_NAMES:
                    continue
                if self._vars_to_read is not None and _var not in self._vars_to_read:
                    logger.info(f"Skipping {_var}")
                    continue
                if _var not in self._data:
                    units = self._variables[_var]
                    data = NpStructuredData(_var, units)
                    self._data[_var] = data

                self._get_data_from_single_file(
                    _file,
                    _var,
                )
        bar.close()

    def metadata(self):
        metadata = dict()
        date = datetime.datetime.min
        for f in self._files:
            with xr.open_dataset(f) as d:
                hist: str = d.attrs.get("history", "")

                datestr = ":".join(hist.split(":")[:3])
                new_date = datetime.datetime.strptime(datestr, "%a %b %d %H:%M:%S %Y")
                if new_date > date:
                    date = new_date

        metadata["revision"] = datetime.datetime.strftime(date, "%y%m%d%H%M%S")

        return metadata

    def _read_file_variables(self, filename) -> dict[str, str]:
        """Returns a mapping of variable name to unit for the dataset.

        Returns:
        --------
        dict[str, str] :
            A dictionary mapping variable name to its corresponding unit.

        """
        variables = {}
        with xr.open_dataset(
            filename,
            decode_cf=False,
        ) as d:
            for vname, var in d.data_vars.items():
                if vname in self._vars_to_read:
                    # Units in pyaro arte by definition strings, but this way
                    # we can make sure that cfunits understands them
                    # otherwise variables[vname] = var.attrs["units"] should work as well
                    variables[vname] = str(cf_units.Unit(var.attrs["units"]))
                    if variables[vname] in UALIASES:
                        variables[vname] = UALIASES[variables[vname]]

        return variables

    def _get_data_from_single_file(
        self,
        file: str,
        varname: str,
    ) -> bool:
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
        dt = xr.load_dataset(file)

        if dt.attrs.get("Conventions", None) != "HARP-1.0":
            raise ValueError(f"File {file} is not a HARP file.")

        values = dt[varname].to_numpy()
        # take station name from filename since there is no name in the data...
        stat_name = os.path.basename(file).split("-")[2]

        values_length = len(values)
        start_time = np.asarray(dt["datetime_start"])
        stop_time = np.asarray(dt["datetime_stop"])
        # start and stop time have been the same in the 1st data revision
        # check that and assume hourly data if it's still the case
        t_diff = stop_time - start_time
        if t_diff.sum() == 0:
            stop_time = stop_time + np.timedelta64(1, "h")
        lat = np.asarray([dt["latitude"]] * values_length)
        long = np.asarray([dt["longitude"]] * values_length)
        station = np.asarray([stat_name] * values_length)
        altitude = np.asarray([dt["altitude"]] * values_length)

        flags = np.asarray([Flag.VALID] * values_length)
        self._data[varname].append(
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

        # fill self._stations

        if not stat_name in self._stations:
            self._stations[stat_name] = Station(
                {
                    "station": stat_name,
                    "longitude": long[0],
                    "latitude": lat[0],
                    "altitude": altitude[0],
                    "country": "NN",
                    "url": "",
                    "long_name": stat_name,
                }
            )

    def _unfiltered_variables(self) -> list[str]:
        """Returns a list of the variable names.

        Returns:
        list[str]
            The list of variable names.
        """
        self.read()
        return list(self._data.keys())

    def _unfiltered_data(self, varname) -> Data:
        self.read()
        return self._data[varname]

    def _unfiltered_stations(self) -> dict[str, Station]:
        self.read()
        return self._stations

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
