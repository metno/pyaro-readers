from typing import Literal
from tqdm import tqdm
from pathlib import Path
from datetime import datetime
from enum import Enum
import os

import numpy as np
import pandas as pd
import xarray as xr

import pyaro

from pyaro.timeseries.AutoFilterReaderEngine import AutoFilterReader, AutoFilterEngine
from pyaro.timeseries import Reader, Data, Station, NpStructuredData


from pyaro_readers.ghostreader.additional_variables import vmr_to_ghost_stations
from pyaro_readers.ghostreader.meta_keys import ghost_meta_keys


import logging


logger = logging.getLogger(__name__)


class Network(Enum):
    EMEP = "EBAS-EMEP"
    GHOST = "GHOST"
    EEA = "EEA_AQ_eReporting"


class GHOSTReader(AutoFilterReader):
    #: List of GHOST metadata keys
    META_KEYS = ghost_meta_keys()

    #: Names of flag variables in GHOST NetCDF files
    FLAG_VARS = ["flag", "qa"]

    #:
    FLAG_DIMNAMES = {"qa": "N_qa_codes", "flag": "N_flag_codes"}

    AUX_REQUIRES = {
        "concco": ["vmrco"],
        "concno": ["vmrno"],
        "concno2": ["vmrno2"],
        "conco3": ["vmro3"],
        "concso2": ["vmrso2"],
    }

    AUX_FUNS = {
        "concco": vmr_to_ghost_stations,
        "concno": vmr_to_ghost_stations,
        "concno2": vmr_to_ghost_stations,
        "conco3": vmr_to_ghost_stations,
        "concso2": vmr_to_ghost_stations,
    }

    DEFAULT_FLAGS_INVALID = {
        "qa": np.asarray(
            [
                [
                    0,
                    1,
                    2,
                    3,
                    6,
                    20,
                    21,
                    22,
                    72,
                    75,
                    82,
                    83,
                    90,
                    91,
                    92,
                    110,
                    111,
                    112,
                    113,
                    115,
                    131,
                    132,
                    133,
                ]
            ]
        ),
        "flag": None,
    }

    FREQ_TO_OFFSET = {
        "hourly": np.timedelta64(1, "h"),
        "hourly_instantaneous": np.timedelta64(1, "h"),
        "daily": np.timedelta64(1, "D"),
        "monthly": np.timedelta64(1, "M"),
    }

    def __init__(
        self,
        filename_or_obj_or_url,
        networks: list[Literal["EBAS-EMEP", "GHOST", "EEA_AQ_eReporting"]] = [
            "EBAS-EMEP"
        ],
        frequency: Literal[
            "hourly", "hourly_instantaneous", "daily", "monthly"
        ] = "daily",
        filters=[],
    ):
        mod_time = Path(filename_or_obj_or_url).stat().st_mtime
        mod_time = datetime.fromtimestamp(mod_time)
        self._revision = f"{mod_time:%Y-%m-%dT%H:%M:%S}"

        self._data_dir = Path(filename_or_obj_or_url)

        self._set_filters(filters)

        self._stations = {}
        self._data = {}

        self._variables = []

        if self._data_dir.is_file():
            raise ValueError("GHOSTReader requires a directory, not a file.")
        if not self._data_dir.exists():
            raise ValueError("GHOSTReader requires an existing directory.")

        self._networks = networks
        self._frequency = frequency

        self._date_filters, self._variable_filters = self._get_pre_processing_filters()

    def get_file_list(self):
        self.files = []
        for network in self._networks:
            path = self._data_dir / network / self._frequency
            var_list = set([f.name for f in path.glob("*") if f.is_dir()])
            if self._variable_filters is not None:
                var_list = (var_list - self._variable_filters["exclude"]) & set(
                    self._variable_filters["include"]
                )

            self._variables = list(var_list)

            possible_dates = []

            if self._date_filters != []:
                for date_tuple in self._date_filters:
                    date_range = pd.date_range(
                        start=date_tuple[0],
                        end=date_tuple[1],
                        freq="MS",
                        inclusive="both",
                    )

                    possible_dates += [
                        f"{d.strftime('%Y%m')}.nc" for d in date_range.to_list()
                    ]

                for var in var_list:
                    for date in possible_dates:
                        file_path = path / var / f"{var}_{date}"
                        if file_path.exists():
                            self.files.append(str(file_path))
            else:
                for var in var_list:
                    for file_path in (path / var).glob(f"{var}_*.nc"):
                        self.files.append(str(file_path))

        self.files = sorted(self.files)
        return self.files

    def _get_pre_processing_filters(self):
        """Create date filters for the data files

        Returns
        -------
        list
            list of date filters

        """
        keepfilters = []
        date_filters = []
        variable_filters = None
        for filter in self._get_filters():
            if isinstance(filter, pyaro.timeseries.Filter.TimeBoundsFilter):
                date_filters.append(filter.envelope())
            elif isinstance(filter, pyaro.timeseries.Filter.VariableNameFilter):
                variable_filters = {
                    "include": filter._include,
                    "exclude": filter._exclude,
                }

            else:
                keepfilters.append(filter)

        self._set_filters(keepfilters)

        # TODO: More sorting to not get non-monotonic time series

        return date_filters, variable_filters

    def get_meta_filename(self, filename):
        """Extract metadata from data filename

        Parameters
        ----------
        filename : str
            data file path or name.

        Returns
        -------
        dict
            dictionary containing var_name, start and stop, and eventually
            also frequency (ts_type)
        """
        var, time = os.path.basename(filename).split(".nc")[0].split("_")

        per = pd.Period(freq="M", year=int(time[:4]), month=int(time[-2:]))
        return dict(var_name=var, start=per.start_time, stop=per.end_time)

    @staticmethod
    def _eval_flags_slice(slc, invalid_flags):
        """
        Compare a flag slice of a data point with input flags marking invalid

        Returns
        -------
        bool
            True, if data point is valid, else False
        """
        if len(np.intersect1d(slc, invalid_flags)) == 0:
            return True
        return False

    def _eval_flags(self, vardata, invalidate_flags, ds):
        valid = np.ones_like(vardata).astype(bool)
        for flagvar in self.FLAG_VARS:
            # check if this flag variable is in input dictionary
            if flagvar in invalidate_flags:
                invalidate = invalidate_flags[flagvar]
                if invalidate is None:
                    continue
                flags = ds[flagvar]
                slice_dim = flags.dims.index(self.FLAG_DIMNAMES[flagvar])

                valid *= np.apply_along_axis(
                    self._eval_flags_slice, slice_dim, flags.values, invalidate
                )
        invalid = ~valid
        return invalid

    def _add_flags_var_to_compute(self, statlist_from_file, var_to_compute):
        for stat in statlist_from_file:
            for i, req in enumerate(self.AUX_REQUIRES[var_to_compute]):
                flags = stat["data_flagged"][req]
                if i == 0:
                    # pointer (safes computation time in case only one variable
                    # is required, i.e. the same flags can be used)
                    stat["data_flagged"][var_to_compute] = flags
                else:
                    logger.warning(
                        "THIS HAS NOT BEEN TESTED AND IS "
                        "SHOULD CURRENTLY NOT BE ABLE "
                        "TO BE REACHED."
                    )
                    current = stat["data_flagged"][var_to_compute].copy()
                    updated = np.logical_or(current, flags)
                    stat["data_flagged"][var_to_compute] = updated
        return statlist_from_file

    def compute_additional_vars(self, statlist_from_file, vars_to_compute):
        """
        Compute additional variables for all sites

        Parameters
        ----------
        statlist_from_file : list
            list of :class:`StationData` objects containing variable data that
            can be read from the data files.
        vars_to_compute : list
            list of variables to be computed from the variables contained in
            `statlist_from_file`.

        Returns
        -------
        statlist_from_file : list
            list of modified :class:`StationData` objects, containing computed
            variables in addition to the data that was contained in them
            initially
        vars_added : list
            list of variables that could be successfully added

        """
        vars_added = []
        for var in vars_to_compute:
            first_stat = statlist_from_file[0]
            can_compute = True
            requires = self.AUX_REQUIRES[var]
            for req in requires:
                if req not in first_stat:
                    can_compute = False
            if can_compute:
                # this will add the variable data to each station data in
                # statlist_from_file
                statlist_from_file = self.AUX_FUNS[var](
                    statlist_from_file, var, *requires
                )
                statlist_from_file = self._add_flags_var_to_compute(
                    statlist_from_file, var
                )

                if var not in vars_added:
                    vars_added.append(var)
        return (statlist_from_file, vars_added)

    def read_file(
        self,
        filename,
        frequency,
        # var_to_read=None,
        # invalidate_flags=None,
    ):
        """Read GHOST NetCDF data file

        Parameters
        ----------
        filename : str
            absolute path to filename to read
        var_name : str, optional
            name of variable to be read, if None, it is inferred from filename

        Returns
        -------
        list
            list of loaded `StationData` objects (dict-like data objects)

        """
        invalidate_flags = self.DEFAULT_FLAGS_INVALID

        var_to_read = self.get_meta_filename(filename)["var_name"]
        # if var_to_read is None:
        # elif var_to_read in self.VARNAMES_DATA:
        #     if var_to_write is None:
        #         var_to_read, var_to_write = self.VARNAMES_DATA[var_to_read], var_to_read
        #     else:
        #         var_to_read = self.VARNAMES_DATA[var_to_read]

        # if var_to_write is None:
        #     var_to_write = self.var_names_data_inv[var_to_read]

        with xr.open_dataset(filename, decode_timedelta=True) as ds:
            if not {"station", "time"}.issubset(ds.dims):  # pragma: no cover
                raise AttributeError("Missing dimensions")
            if "station_name" not in ds:  # pragma: no cover
                raise AttributeError("No variable station_name found")

            # get all station metadata values as numpy arrays, since xarray isel,
            # __getitem__, __getattr__ are slow... this can probably be solved
            # more elegantly
            meta_glob = {}
            for meta_key in self.META_KEYS:
                try:
                    meta_glob[meta_key] = ds[meta_key].values
                except KeyError:  # pragma: no cover
                    logger.warning(
                        f"No such metadata key in GHOST data file: {Path(filename).name}"
                    )

            # for meta_key, to_unit in self.CONVERT_UNITS_META.items():
            #     from_unit = ds[meta_key].attrs["units"]

            #     meta_glob[meta_key] = convert_unit(
            #         meta_glob[meta_key], from_unit=from_unit, to_unit=to_unit
            #     )

            tvals = ds["time"].values

            vardata = ds[var_to_read]  # DataArray
            varinfo = vardata.attrs

            units = varinfo["units"]

            # ToDo: it is important that station comes first since we use numpy
            # indexing below and not xarray.isel or similar, due to performance
            # issues. This may need to be updated in case of profile data.
            assert vardata.dims == ("station", "time")
            data_np = vardata.values

            # evaluate flags
            invalid = self._eval_flags(vardata, invalidate_flags, ds)

            for idx in ds.station.values:
                name = str(ds.station_name.values[idx])

                lat = meta_glob["latitude"][idx]
                lon = meta_glob["longitude"][idx]
                alt = meta_glob["altitude"][idx]
                if name not in self._stations:
                    self._stations[name] = Station(
                        {
                            "station": name,
                            "longitude": lon,
                            "latitude": lat,
                            "altitude": alt,
                            "country": meta_glob["country"][idx],
                            "url": "",
                            "long_name": name,
                        }
                    )

                if var_to_read in self._data:
                    da = self._data[var_to_read]
                    if da.units != units:
                        raise Exception(f"unit change from '{da.units}' to 'units'")
                else:
                    da = NpStructuredData(var_to_read, units)
                    self._data[var_to_read] = da

                start = tvals

                end = start

                end = start + self.FREQ_TO_OFFSET[frequency]
                self._data[var_to_read].append(
                    data_np[idx, :],
                    np.full(data_np.shape[1], fill_value=name),
                    np.ones(data_np.shape[1]) * lat,
                    np.ones(data_np.shape[1]) * lon,
                    np.ones(data_np.shape[1]) * alt,
                    start,
                    end,
                    ~invalid[idx, :],
                    np.ones(data_np.shape[1]) * np.nan,
                )

    def read(
        self,
    ):
        for i in tqdm(
            self.get_file_list(), desc="Reading GHOST data files", unit="file"
        ):
            self.read_file(
                filename=i,
                frequency=self._frequency,
            )

    def metadata(self) -> dict[str, str]:
        return {"revision": self._revision}

    def _unfiltered_data(self, varname: str):
        self.read()
        return self._data[varname]

    def _unfiltered_stations(self) -> dict[str, Station]:
        return self._stations

    def _unfiltered_variables(self) -> list[str]:
        self.get_file_list()
        return list(self._variables)

    def close(self):
        pass


class GHOSTTimeseriesEngine(AutoFilterEngine):
    def description(self) -> str:
        return """GHOST reader
        """

    def url(self) -> str:
        return "https://essd.copernicus.org/articles/16/4417/2024/essd-16-4417-2024-discussion.html"

    def reader_class(self) -> Reader:
        return GHOSTReader


if __name__ == "__main__":
    d = "/home/danielh/Documents/pyaerocom/projects/ghost/data/data/EBAS-EMEP/daily/pm10/pm10_201905.nc"

    reader = GHOSTReader(
        filename_or_obj_or_url="/home/danielh/Documents/pyaerocom/projects/ghost/data/data/",
        networks=["EBAS-EMEP"],
        frequency="daily",
        filters={
            "time_bounds": {
                "startend_include": [
                    ("2019-01-01 00:00:00", "2019-01-02 00:00:00")
                ],  # Include data between these time bounds
            },
            "variables": {"include": ["pm10", "pm2p5"], "exclude": ["pm10"]},
        },
    )

    reader.read()

    breakpoint()
