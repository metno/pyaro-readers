import tarfile
from typing import Literal
from tqdm import tqdm
from pathlib import Path
from datetime import datetime


import numpy as np
import pandas as pd
import xarray as xr

import pyaro

from pyaro.timeseries.AutoFilterReaderEngine import AutoFilterReader, AutoFilterEngine
from pyaro.timeseries import Reader, Data, Station, NpStructuredData


from pyaro_readers.ghostreader.meta_keys import ghost_meta_keys
from pyaro_readers.ghostreader.ghost_options import (
    AREA_CLASS,
    STATION_CLASS,
    # MEASUREMENT_METHODS,
    NETWORKS,
)


import logging


logger = logging.getLogger(__name__)


class GHOSTReader(AutoFilterReader):
    #: List of GHOST metadata keys
    META_KEYS = ghost_meta_keys()

    #: Names of flag variables in GHOST NetCDF files
    FLAG_VARS = ["flag", "qa"]

    #:
    FLAG_DIMNAMES = {"qa": "N_qa_codes", "flag": "N_flag_codes"}

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
        networks: list[str] = ["EBAS-EMEP"],
        frequency: Literal[
            "hourly", "hourly_instantaneous", "daily", "monthly"
        ] = "daily",
        joly_peuch_min_max: tuple[int, int] | None = None,
        measurement_methods: list[str] = [],
        use_prefiltered=True,
        compressed: bool = True,
        area_classifications=[],
        station_classifications=[],
        filters=[],
    ):

        if isinstance(networks, str):
            networks = [networks]

        if not set(networks).issubset(set(NETWORKS)):
            raise ValueError(
                f"Invalid networks: {networks}. Use one of the following: {NETWORKS}"
            )

        mod_time = Path(filename_or_obj_or_url).stat().st_mtime
        mod_time = datetime.fromtimestamp(mod_time)
        self._revision = f"{mod_time:%Y-%m-%dT%H:%M:%S}"

        self._data_dir = Path(filename_or_obj_or_url)

        self._set_filters(filters)

        self._stations = {}
        self._data = {}

        self._variables = []

        if compressed:
            logger.info("GHOSTReader initialized in compressed mode.")
        self._compressed = compressed

        self._use_prefiltered = use_prefiltered

        if joly_peuch_min_max is not None:
            if area_classifications != [] or station_classifications != []:
                raise ValueError(
                    "Joly-Peuch min/max values can only be set if no area or station classifications are provided."
                )

            if not isinstance(joly_peuch_min_max, tuple):
                raise ValueError("Joly-Peuch min/max values must be a tuple.")

            if joly_peuch_min_max[0] < 1 or joly_peuch_min_max[1] > 10:
                raise ValueError("Joly-Peuch min/max values must be between 1 and 10.")

            if len(joly_peuch_min_max) != 2:
                raise ValueError(
                    "Joly-Peuch min/max values must be a tuple of (min, max)."
                )
            if joly_peuch_min_max[0] >= joly_peuch_min_max[1]:
                raise ValueError("Joly-Peuch min must be smaller than max.")

        self._joly_peuch_min_max = joly_peuch_min_max

        if area_classifications != []:
            for ac in area_classifications:
                if ac not in AREA_CLASS:
                    raise ValueError(
                        f"Invalid area classifications: {area_classifications}. Use one of the following: {AREA_CLASS}"
                    )
        if station_classifications != []:
            for sc in station_classifications:
                if sc not in STATION_CLASS:
                    raise ValueError(
                        f"Invalid station classifications: {station_classifications}. Use one of the following: {STATION_CLASS}"
                    )

        self._measurement_methods = measurement_methods
        self._area_classifications = area_classifications
        self._station_classifications = station_classifications

        if self._data_dir.is_file():
            raise ValueError("GHOSTReader requires a directory, not a file.")
        if not self._data_dir.exists():
            raise ValueError("GHOSTReader requires an existing directory.")

        self._networks = networks
        self._frequency = frequency

        self._date_filters, self._variable_filters = self._get_pre_processing_filters()

    def get_zipped_file_list(self) -> dict[str, dict[Path, list[tarfile.TarInfo]]]:
        self.files = {}

        for network in self._networks:
            path = self._data_dir / network / self._frequency
            var_list = set(
                [f.with_suffix("").stem for f in path.glob("*.tar.xz") if f.is_file()]
            )
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
                if var not in self.files:
                    self.files[var] = {}
                for file in path.glob(f"{var}.tar.xz"):
                    self.files[var][file] = []
                    with tarfile.open(file, "r:xz") as tar_ref:
                        for member in tar_ref.getmembers():
                            if member.isdir():
                                continue
                            date = member.name.split("/")[-1].split(f"{var}_")[-1]
                            if possible_dates:
                                if date in possible_dates:
                                    self.files[var][file].append(member)
                            else:
                                self.files[var][file].append(member)

        self.files = {
            k: {fk: sorted(fv, key=lambda x: x.name) for fk, fv in v.items()}
            for k, v in self.files.items()
        }
        return self.files

    def get_file_list(self) -> dict[str, list[Path]]:
        self.files = {}

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
                    if var not in self.files:
                        self.files[var] = []
                    for date in possible_dates:
                        file_path = path / var / f"{var}_{date}"
                        if file_path.exists():
                            self.files[var].append(str(file_path))
            else:
                for var in var_list:
                    if var not in self.files:
                        self.files[var] = []

                    for file_path in (path / var).glob(f"{var}_*.nc"):
                        self.files[var].append(str(file_path))

        self.files = {k: sorted(v) for k, v in self.files.items()}
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

    def _get_filter_mask(self, ds: xr.Dataset) -> np.ndarray:
        """
        Gets mask for filtering stations based on Joly-Peuch classification, area classification, station classification and measurement method.
        """

        nb_stations = len(ds["station"].values)

        if self._joly_peuch_min_max:
            joly_peuch_min, joly_peuch_max = self._joly_peuch_min_max
            joly_peuch_mask = (
                (ds["Joly-Peuch_classification_code"] >= joly_peuch_min)
                & (ds["Joly-Peuch_classification_code"] <= joly_peuch_max)
                & (ds["Joly-Peuch_classification_code"].notnull())
            )
        else:
            joly_peuch_mask = np.ones(nb_stations, dtype=bool)

        if self._measurement_methods:
            mm_mask = ds["measurement_methodology"].isin(self._measurement_methods)
        else:
            mm_mask = np.ones(nb_stations, dtype=bool)

        if self._area_classifications:
            area_mask = ds["area_classification"].isin(self._area_classifications)
        else:
            area_mask = np.ones(nb_stations, dtype=bool)

        if self._station_classifications:
            station_mask = ds["station_classification"].isin(
                self._station_classifications
            )
        else:
            station_mask = np.ones(nb_stations, dtype=bool)

        total_mask = joly_peuch_mask & area_mask & station_mask & mm_mask

        return total_mask

    def read_file(
        self,
        filename_or_obj,
        frequency,
        var_to_read,
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

        decode_times = False if self._frequency == "monthly" else True

        with xr.open_dataset(
            filename_or_obj, decode_timedelta=True, decode_times=decode_times
        ) as ds:
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
                    logger.warning("No such metadata key in GHOST data file")

            total_mask = self._get_filter_mask(ds)
            var_key = (
                f"{var_to_read}_prefiltered_defaultqa"
                if self._use_prefiltered
                else var_to_read
            )

            tvals = ds["time"].values
            if self._frequency == "monthly":
                # for monthly data, we set the time to the first day of the month, since the time variable is just a string with the month and year

                st = pd.to_datetime(ds.time.units.split(" ")[2], format="%Y-%m-%d")
                tvals = np.array(
                    [
                        (st + pd.DateOffset(months=int(t))).to_datetime64()
                        for t in tvals
                    ],
                    dtype="datetime64[M]",
                )

            vardata = ds[var_key]  # DataArray
            varinfo = vardata.attrs

            units = varinfo["units"]

            # ToDo: it is important that station comes first since we use numpy
            # indexing below and not xarray.isel or similar, due to performance
            # issues. This may need to be updated in case of profile data.
            assert vardata.dims == ("station", "time")
            data_np = vardata.values[total_mask]

            if not self._use_prefiltered:
                # evaluate flags
                invalid = self._eval_flags(vardata, invalidate_flags, ds)[total_mask]
            else:
                invalid = np.zeros_like(data_np).astype(bool)

            if var_to_read in self._data:
                da = self._data[var_to_read]
                if da.units != units:
                    raise Exception(f"unit change from '{da.units}' to 'units'")
            else:
                da = NpStructuredData(var_to_read, units)
                self._data[var_to_read] = da

            names = ds.station_reference.values.astype(str)[total_mask]
            lat = ds["latitude"].values[total_mask]
            lon = ds["longitude"].values[total_mask]
            alt = ds["altitude"].values[total_mask]
            country = ds["country"].values[total_mask]

            for name in set(names) - set(self._stations.keys()):
                idx = np.where(names == name)[0][0]

                if name not in self._stations:
                    self._stations[name] = Station(
                        {
                            "station": name,
                            "longitude": lon[idx],
                            "latitude": lat[idx],
                            "altitude": alt[idx],
                            "country": country[idx],
                            "url": "",
                            "long_name": name,
                        }
                    )

            start = tvals

            flattened_data = data_np.flatten()
            flattened_invalid = invalid.flatten()

            end = start + self.FREQ_TO_OFFSET[frequency]

            self._data[var_to_read].append(
                flattened_data,
                np.repeat(names, data_np.shape[1]),
                np.repeat(lat, data_np.shape[1]),
                np.repeat(lon, data_np.shape[1]),
                np.repeat(alt, data_np.shape[1]),
                np.repeat(start, data_np.shape[0]),
                np.repeat(end, data_np.shape[0]),
                ~flattened_invalid,
                np.ones_like(flattened_data) * np.nan,
            )

    def read(
        self,
    ):
        if self._compressed:
            file_dict = self.get_zipped_file_list()

            for var in file_dict:
                for file in file_dict[var]:
                    with tarfile.open(file, "r:xz") as tar_ref:
                        for member in tqdm(
                            file_dict[var][file],
                            desc=f"Reading compressed GHOST data files for {var}",
                            unit="file",
                        ):
                            f = tar_ref.extractfile(member)
                            self.read_file(
                                filename_or_obj=f.read(),
                                frequency=self._frequency,
                                var_to_read=var,
                            )
        else:
            file_dict = self.get_file_list()

            for var in file_dict:
                for file in tqdm(
                    file_dict[var],
                    desc=f"Reading GHOST data files for {var}",
                    unit="file",
                ):
                    self.read_file(
                        filename_or_obj=file,
                        frequency=self._frequency,
                        var_to_read=var,
                    )

    def metadata(self) -> dict[str, str]:
        return {"revision": self._revision}

    def _unfiltered_data(self, varname: str):
        if self._data == {}:
            self.read()
        return self._data[varname]

    def _unfiltered_stations(self) -> dict[str, Station]:
        if self._data == {} and self._stations == {}:
            self.read()
        return self._stations

    def _unfiltered_variables(self) -> list[str]:
        # self.get_file_list()
        if self._compressed:
            return list(self.get_zipped_file_list().keys())
        return list(self.get_file_list().keys())

    def close(self):
        pass

    @staticmethod
    def get_classification_options():
        return {
            "area_classifications": AREA_CLASS,
            "station_classifications": STATION_CLASS,
        }

    @staticmethod
    def get_network_options():
        return NETWORKS


class GHOSTTimeseriesEngine(AutoFilterEngine):
    def description(self) -> str:
        return """GHOST reader
        """

    def url(self) -> str:
        return "https://essd.copernicus.org/articles/16/4417/2024/essd-16-4417-2024-discussion.html"

    def reader_class(self) -> Reader:
        return GHOSTReader
