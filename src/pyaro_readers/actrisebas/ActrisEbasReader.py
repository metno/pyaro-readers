import datetime
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlparse, quote
import sys

if sys.version_info >= (3, 11):  # pragma: no cover
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

import numpy as np
import numpy.typing as npt
import polars
import xarray as xr
from tqdm import tqdm
from urllib3.poolmanager import PoolManager
from urllib3.util.retry import Retry

from pyaro.timeseries import (
    AutoFilterReaderEngine,
    Data,
    Flag,
    NpStructuredData,
    Station,
    Reader,
    Filter,
)

logger = logging.getLogger(__name__)

# default API URL base
# BASE_API_URL = "https://dev-actris-md2.nilu.no/"
BASE_API_URL = "https://prod-actris-md2.nilu.no/"
# base URL to query for data for a certain variable
VAR_QUERY_URL = f"{BASE_API_URL}metadata/content/"
# basename of definitions.toml which connects the pyaerocom variable names with the ACTRIS variable names
DEFINITION_FILE_BASENAME = "definitions.toml"
# online ressource of ebas flags
EBAS_FLAG_URL = "https://folk.nilu.no/~ebas/EBAS_Masterdata/ebas_flags.csv"

DEFINITION_FILE = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), DEFINITION_FILE_BASENAME
)
# name of the standard_name section in the DEFINITION_FILE
STD_NAME_SECTION_NAME = "actris_standard_names"

# name of the ebas section in the DEFINITION_FILE
EBAS_VAR_SECTION_NAME = "variables"

# Only variables having these cell methods are considered data variables
CELL_METHODS_TO_COPY = [
    "time: mean",
    "time: median",
    "time: detection limit",
    "time: sum",
]

# number of times an api  request is tried before we consider it failed
MAX_RETRIES = 2

# number used instead of NaN in flags
# in the netcdf files there's actually a zero, but there's also a _FillValue attribute that sets that to NaN again
EBAS_FLAG_NAN_NUMBER = 0

# name of the root key containing the download information
DISTRIBUTION_ROOT_KEY = "md_distribution_information"
DISTRIBUTION_PROTOCOL_KEY = "protocol"
DISTRIBUTION_PROTOCOL_NAME_OPENDAP = "OPeNDAP".lower()
DISTRIBUTION_PROTOCOL_NAME_HTTP = "http".lower()
DISTRIBUTION_URL_KEY = "dataset_url"

# some info to get to station name and location
LOCATION_ROOT_KEY = "md_data_identification"
LOCATION_FACILITY_KEY = "facility"
LOCATION_NAME_KEY = "name"
LOCATION_LAT_KEY = "lat"
LOCATION_LON_KEY = "lon"
LOCATION_ALT_KEY = "alt"

# Keys to get to the time coverage of an URL
TIME_COVERAGE_ROOT_KEY = "ex_temporal_extent"
TIME_COVERAGE_START_KEY = "time_period_begin"
TIME_COVERAGE_END_KEY = "time_period_end"

# name of netcdf time variable in the netcdf files
# should be "time" as of CF convention, but other names can be added here
TIME_VAR_NAME = ["time"]

CACHE_ENVIRONMENT_VAR_NAME = "PYARO_CACHE_DIR_EBAS_ACTRIS"

# to read only observations
PRODUCT_TYPE_ROOT_KEY = "md_actris_specific"
PRODUCT_TYPE_KEY = "product_type"
PRODUCT_TYPES_TO_COPY = [
    "observation",
]

# define CF versions of the EBAS units
CF_UNITS = {}
CF_UNITS["ug/m3"] = "ug m-3"
CF_UNITS["nmol/mol"] = "nmol mol-1"
CF_UNITS["mm"] = "mm d-1"
CF_UNITS["mg/l"] = "mg S m-2 d-1"
# CF_UNITS[""] = ""


class ActrisEbasStdNameNotFoundException(Exception):
    pass


class ActrisEbasQcVariableNotFoundException(Exception):
    pass


class ActrisEbasTimeSeriesReader(AutoFilterReaderEngine.AutoFilterReader):
    def __init__(
        self,
        filename_or_obj_or_url=BASE_API_URL,
        filters=[],
        # tqdm_desc: str | None = None,
        # ts_type: str = "daily",
        test_flag: bool = False,
        cache_flag: bool = True,
        extract_http_urls: bool = False,
        remove_non_pyaerocom_time_steps: bool = True,
    ):
        """ """
        self._filename = None
        self._stations = {}
        # dict with station name as key and a list of opendap urls as values
        self.open_dap_urls_to_dl = {}
        # dict with station name as key and a list of download urls as values
        # the urls need to be read using the http protocol
        self.dl_urls_to_dl = {}
        # time coverage from the API; keys are the URL
        self.time_coverages = {}
        self._data = {}  # var -> {data-array}
        self._set_filters(filters)
        # self._header = []
        self._metadata = {}
        self._tmp_metadata = {}
        # used for variable matching in the EBAS data files
        # gives a mapping between the EBAS or pyaerocom variable name
        # and the CF standard name found in the EBAS data files
        # Due to standard_names aliases, the values are a list
        self.standard_names: dict[str, list[str]] = {}
        # _laststatstr = ""
        self._revision = datetime.datetime.now()
        self._metadata["revision"] = datetime.datetime.strftime(
            self._revision, "%y%m%d%H%M%S"
        )
        self._tmp_metadata["revision"] = datetime.datetime.strftime(
            self._revision, "%y%m%d%H%M%S"
        )
        self.ebas_valid_flags = self.get_ebas_valid_flags()
        self.sites_to_read = []
        self.sites_to_exclude = []
        self.vars_to_read = None
        self.units = None
        self.times_to_read = (np.datetime64(1, "Y"), np.datetime64(120, "Y"))
        # keep pyaerocom based stuff optional
        try:
            import pyaerocom.exceptions
            from pyaerocom.units.datetime import TsType

            self.remove_non_pyaerocom_time_steps = remove_non_pyaerocom_time_steps
        except ImportError:
            self.remove_non_pyaerocom_time_steps = False

        self.cache_dir = None
        try:
            _cache_dir = Path(os.environ[CACHE_ENVIRONMENT_VAR_NAME])
            if _cache_dir.exists():
                self.cache_flag = cache_flag
                self.cache_dir = _cache_dir
        except KeyError:
            self.cache_flag = False

        # set filters
        for filter in self._get_filters():
            # pyaro filters...
            if isinstance(filter, Filter.StationFilter):
                self.sites_to_read = filter.init_kwargs()["include"]
                self.sites_to_exclude = filter.init_kwargs()["exclude"]
            elif isinstance(filter, Filter.VariableNameFilter):
                self.vars_to_read = filter.init_kwargs()["include"]
                logger.info(f"applying variable include filter {self.vars_to_read}...")
            elif isinstance(filter, Filter.TimeBoundsFilter):
                # this is not the full implementation. Correct filtering will be done
                # by pyaro
                if filter.has_envelope():
                    self.times_to_read = filter.envelope()
                else:
                    # No filtering of time
                    pass
                logger.info(f"applying time include filter {self.times_to_read}...")
            else:
                # pass on not reader supported filters
                pass

        if self.vars_to_read is None:
            logger.info(f"No variable filter given, nothing to read...")
            self.vars_to_read = []

        # read config file
        self.def_data = self._read_definitions(file=DEFINITION_FILE)
        # Because the user might have given a pyaerocom name, build self.actris_vars_to_read with a list
        # of ACTRIS variables to read. values are a list
        self.actris_vars_to_read = {}
        for var in self.vars_to_read:
            self._tmp_metadata[var] = {}
            # handle pyaerocom variables here:
            # if a given variable name is in the list of pyaerocom variable names in definitions.toml
            self.actris_vars_to_read[var] = []
            if var in self.def_data["variables"]:
                # user gave a pyaerocom variable name
                self.actris_vars_to_read[var] = self.def_data["variables"][var][
                    "actris_variable"
                ]
                for _actris_var in self.actris_vars_to_read[var]:
                    try:
                        self.standard_names[_actris_var] = self.get_ebas_standard_name(
                            var
                        )
                    except KeyError:
                        logger.info(
                            f"No ebas standard names found for {var}. Trying those of the actris variable {self.actris_vars_to_read[var][0]} instead..."
                        )
                        self.standard_names[_actris_var] = (
                            self.get_actris_standard_name(_actris_var)
                        )

            else:
                # user gave ACTRIS name
                self.actris_vars_to_read[var].append(var)
                self.standard_names[var] = self.get_actris_standard_name(var)

        for _pyaro_var in self.actris_vars_to_read:
            self._metadata[_pyaro_var] = {}
            for _actris_var in self.actris_vars_to_read[_pyaro_var]:
                # for testing since the API was error-prone and slow in the past.
                # might also be useful for caching at some point, but for now test_file
                # never exists
                test_file = os.path.join(
                    os.path.dirname(os.path.realpath(__file__)),
                    f"{_actris_var}.json",
                )
                if os.path.exists(test_file) and test_flag:
                    with open(test_file, "r") as f:
                        json_resp = json.load(f)
                else:
                    page_no = 0
                    json_resp_tmp = "bla"
                    json_resp = []
                    while len(json_resp_tmp) != 0:
                        # search for variable metadata
                        query_url = f"{VAR_QUERY_URL}{quote(self.actris_vars_to_read[_pyaro_var][0])}/page/{page_no}"
                        logger.info(query_url)
                        retries = Retry(connect=5, read=2, redirect=5)
                        http = PoolManager(retries=retries)
                        response = http.request("GET", query_url)
                        if len(response.data) > 0:
                            try:
                                json_resp_tmp = json.loads(
                                    response.data.decode("utf-8")
                                )
                            except json.decoder.JSONDecodeError:
                                json_resp_tmp = json.loads(response.data)

                            json_resp.extend(json_resp_tmp)
                            page_no += 1
                        else:
                            json_resp_tmp = ""
                            continue

                self._tmp_metadata[_pyaro_var][_actris_var] = json_resp
                # extract opendap urls
                self.open_dap_urls_to_dl[_actris_var] = self.extract_opendap_info(
                    json_resp,
                    sites_to_read=self.sites_to_read,
                    sites_to_exclude=self.sites_to_exclude,
                )
                if extract_http_urls:
                    # extract download urls (to be read using http) urls
                    # these are unused atm, but might serve as a sanity check later on
                    self.dl_urls_to_dl[_actris_var] = self.extract_dl_url_info(
                        json_resp,
                        sites_to_read=self.sites_to_read,
                        sites_to_exclude=self.sites_to_exclude,
                    )

                assert self._tmp_metadata[_pyaro_var][_actris_var]

    def metadata(self):
        return self._metadata

    def _read(
        self,
        tqdm_desc="reading stations",
    ):
        """
        read the data from EBAS thredds server (or the local cache)
        """
        # some inits to avoid the IDE complaining about not initialised variables
        stat_code = None
        _local_file = None
        valid_idxs = []
        # for actris vocabulary key and value of self.actris_vars_to_read are the same
        # for pyaerocom vocabulary they are not (key is pyaerocom variable name there)!
        for _var in self.actris_vars_to_read:
            if _var in self._data:
                logger.info(f"var {_var} already read")
                continue
            for actris_variable in self.actris_vars_to_read[_var]:
                urls_to_dl = self.open_dap_urls_to_dl[actris_variable]
                bar = tqdm(desc=tqdm_desc, total=len(urls_to_dl), disable=None)
                for s_idx, site_name in enumerate(urls_to_dl):
                    self._metadata[site_name] = {}

                    for f_idx, thredds_url in enumerate(urls_to_dl[site_name]):
                        _local_file_flag = False
                        # time coverage per URL is in the API response
                        # but build a fall back in case that's not working
                        get_coverage_from_url_flag = False
                        try:
                            file_start_time = self.time_coverages[thredds_url][0]
                            file_end_time = self.time_coverages[thredds_url][1]
                            # check for time coverage from API response
                            # the same code appears later on for data read from the data file...
                            if (
                                file_end_time < self.times_to_read[0]
                                or file_start_time > self.times_to_read[1]
                            ):
                                logger.info(
                                    f"url {thredds_url} not read. Outside of time bounds."
                                )
                                continue

                        except Exception as e:
                            logger.error(
                                f"failed to read time coverage for {thredds_url} from API response. reading the data URL instead."
                            )
                            get_coverage_from_url_flag = True

                        if self.cache_flag:
                            _local_file = self.cache_dir / "_".join(
                                Path(thredds_url).parts[-4:]
                            )
                            if _local_file.exists():
                                url = _local_file
                                _local_file_flag = True
                            else:
                                url = thredds_url
                        else:
                            url = thredds_url
                        try:
                            logger.info(f"trying to read URL {url}")
                            tmp_data = xr.open_dataset(url)
                            logger.info(f"Successfully read URL {url}")
                        except Exception as e:
                            logger.error(f"failed to read {url} with error {e}")
                            assert url
                            continue

                        # determining time coverage from the data file...
                        # still in the code because we are unsure about the quality of the API response
                        if get_coverage_from_url_flag:
                            file_start_time = np.min(
                                np.asarray(tmp_data["time_bnds"][:, 0])
                            )
                            file_end_time = np.max(
                                np.asarray(tmp_data["time_bnds"][:, 1])
                            )

                            if (
                                file_end_time < self.times_to_read[0]
                                or file_start_time > self.times_to_read[1]
                            ):
                                logger.info(
                                    f"url {url} not read. Outside of time bounds."
                                )
                                continue
                        # write cache file if needed
                        if self.cache_flag and not _local_file_flag:
                            # some of the data files can't be read by xarray due to errors. So we
                            # can't cache them (all data is only realized here)
                            try:
                                tmp_data.load()
                                tmp_data.to_netcdf(_local_file)
                                logger.info(f"saved cache file {_local_file}")
                            except Exception as e:
                                logger.error(
                                    f"failed to save cache file {_local_file} with error {e}"
                                )
                                logger.error(f"URL: {url}. Ignoring that URL.")
                                try:
                                    _local_file.unlink()
                                except Exception:
                                    pass
                                tmp_data.close()
                                continue

                        # read needed data
                        for d_idx, _data_var in enumerate(
                            self._get_ebas_data_vars(
                                tmp_data,
                            )
                        ):
                            stat_code = None
                            # look for a standard_name match and return only that variable
                            std_name = self.get_ebas_data_standard_name(
                                tmp_data, _data_var
                            )
                            if std_name not in self.standard_names[actris_variable]:
                                # logger.info(
                                #     f"station {site_name}, file #{f_idx}: skipping variable {_data_var} due to wrong standard name"
                                # )
                                continue
                            else:
                                log_str = f"station {site_name}, file #{f_idx}: found matching standard_name {std_name}"
                                logger.info(log_str)

                            # check for time steps not fitting pyaerocom
                            start_time = np.asarray(tmp_data["time_bnds"][:, 0])
                            stop_time = np.asarray(tmp_data["time_bnds"][:, 1])
                            ts_no_all = len(start_time)
                            # if we need to remove non pyaerocom time step sizes
                            if self.remove_non_pyaerocom_time_steps:

                                valid_idxs = self.get_valid_ts_indizes(
                                    start_time, stop_time
                                )
                                ts_no = len(valid_idxs)
                                if ts_no == 0:
                                    ts_type = self.get_pyaerocom_ts_sizes(
                                        start_time, stop_time
                                    )
                                    logger.info(
                                        f"all timesteps of URL {url} were non standard lengths (e.g. {ts_type[0]}). Skipping this URL..."
                                    )
                                    continue
                            else:
                                ts_no = ts_no_all

                            # Not all files contain height information unfortunately
                            # skip those that don't
                            try:
                                altitude = np.full(
                                    ts_no, tmp_data.attrs["geospatial_vertical_min"]
                                )
                            except KeyError as e:
                                logger.error(
                                    f"URL: {url} contains no height information. Skipping this URL."
                                )
                                continue

                            # units...
                            # logs if netcdf-CF units and EBAS units are not equal
                            self.units = self.get_ebas_data_units(
                                tmp_data, _data_var, url
                            )

                            long_name = tmp_data.attrs["ebas_station_name"]
                            # the station name from the API might not match the one from the data file
                            # always use the one from the API, but keep the line above for documentation
                            # we might decide later on to use the name from the data file instead
                            if long_name != site_name:
                                long_name = site_name
                            stat_code = tmp_data.attrs["ebas_station_code"]
                            # create variables valid for all measured variables...
                            lat = np.full(ts_no, tmp_data.attrs["geospatial_lat_min"])
                            lon = np.full(ts_no, tmp_data.attrs["geospatial_lon_min"])
                            # station = np.full(ts_no, tmp_data.attrs["ebas_station_code"])
                            station = np.full(ts_no, long_name)
                            # Unused at this point
                            standard_deviation = np.full(ts_no, np.nan)

                            # check if the read variable is a composition variable like deposition
                            if (
                                "standard_names_2nd_var"
                                in self.def_data["variables"][_var]
                            ):
                                try:
                                    vals, ebas_flags, self.units = self.calc_var(
                                        tmp_data, _data_var, _var
                                    )
                                except ActrisEbasStdNameNotFoundException:
                                    logger.info(
                                        f"URL: {url} no precipitation found for deposition calculation."
                                    )
                                    continue
                            else:
                                vals = tmp_data[_data_var].values
                                ebas_flags = self.get_ebas_var_flags(
                                    tmp_data, _data_var
                                )

                            # apply flags
                            # quick test if we need to apply flags at all
                            if (
                                np.nansum(ebas_flags)
                                == ebas_flags.size * EBAS_FLAG_NAN_NUMBER
                            ):
                                flags = np.full(ts_no_all, Flag.VALID, dtype="i2")
                            else:
                                vals, flags = self.get_var_data_flags_applied_from_vars(
                                    vals, ebas_flags
                                )

                            # remove non-standard time step sizes if needed
                            if ts_no_all > ts_no:
                                try:
                                    flags = flags[valid_idxs]
                                except Exception as e:
                                    logger.error(
                                        f"failed to set flags right for {site_name} with error {e}"
                                    )
                                start_time = start_time[valid_idxs]
                                stop_time = stop_time[valid_idxs]
                                vals = vals[valid_idxs]

                            if _var not in self._data:
                                self._data[_var] = NpStructuredData(
                                    _var,
                                    self.units,
                                )

                            self._data[_var].append(
                                value=vals,
                                station=station,
                                latitude=lat,
                                longitude=lon,
                                altitude=altitude,
                                start_time=start_time,
                                end_time=stop_time,
                                flag=flags,
                                standard_deviation=standard_deviation,
                            )
                            # stop after the 1st matching variable
                            logger.info(
                                f"matching std_name found. Not searching for possible additional std_name matches at this point..."
                            )
                            break
                        if stat_code is not None:
                            # if site_name == "Carnsore Point":
                            if site_name == "Hallahus":
                                assert site_name
                            if not site_name in self._stations:
                                # exception in case all time step sizes were not pyaerocom compatible
                                try:
                                    self._stations[site_name] = Station(
                                        {
                                            "station": stat_code,
                                            "longitude": lon[0],
                                            "latitude": lat[0],
                                            "altitude": altitude[0],
                                            "country": self.get_ebas_data_country_code(
                                                tmp_data
                                            ),
                                            "url": "",
                                            # This is used by pyaerocom
                                            "long_name": site_name,
                                        }
                                    )
                                except UnboundLocalError:
                                    logger.info(
                                        f"site_name: {site_name} all time steps for variable {_var} were non pyaerocom standard."
                                    )
                                    continue
                    try:
                        tmp_data.close()
                    except Exception as e:
                        pass
                    bar.update(1)

                bar.close()
        assert True

    def remove_non_pyaerocom_ts_step_sizes(self):
        """
        helper method to remove time step sizes not understood by pyaerocom
        using pyaerocom functionality to determine these sizes
        """
        pass

    def interpolate_non_pyaerocom_ts_step_sizes(self):
        """
        helper method to interpolate time step sizes not understood by pyaerocom
        to the next higher resolution time step size
        """
        pass

    def get_valid_ts_indizes(
        self,
        start_time: npt.NDArray[np.datetime64],
        stop_time: npt.NDArray[np.datetime64],
    ):
        """
        helper method to get the indices of valid time step sizes form the start and the end times

        :param start:
        start time
        :param end:
        end time
        :return:
        :type TS
        """
        from pyaerocom.units.datetime.time_config import (
            TS_TYPES,
        )

        pass
        ts_types = self.get_pyaerocom_ts_sizes(start_time, stop_time)
        retlist = []
        for i_idx in range(len(ts_types)):
            if ts_types[i_idx] in TS_TYPES:
                retlist.append(i_idx)

        return retlist

    def get_pyaerocom_ts_sizes(
        self, start: npt.NDArray[np.datetime64], end: npt.NDArray[np.datetime64]
    ):
        """
        helper method to get pyaerocom time step sizes

        :return:
        """
        import functools
        import pyaerocom.exceptions
        from pyaerocom.units.datetime import TsType

        def _calculate_ts_type(
            start: npt.NDArray[np.datetime64], end: npt.NDArray[np.datetime64]
        ) -> npt.NDArray[TsType]:
            seconds = (end - start).astype("timedelta64[s]").astype(np.int64)

            @np.vectorize(otypes=[TsType])
            @functools.lru_cache(maxsize=128)
            def memoized_ts_type(x: np.int32) -> TsType:
                if x == 0:
                    return TsType("hourly")
                try:
                    return TsType.from_total_seconds(x)
                except pyaerocom.exceptions.TemporalResolutionError:
                    return

            return memoized_ts_type(seconds)

        return _calculate_ts_type(start, end)

    def get_ebas_var_flags(self, tmp_data, _data_var):
        """helper method to return ebas flags for _data_var"""

        # what's done here is a bit special:
        # in the netcdf file the data type is int
        # but in the attributes there's a _FillValue attribute
        # Because there's no NaN for integers the netcdf library then converts the integer to
        # float.
        # Because we will work a lot with these flags, we remove the NaNs,
        # put it to the original 0, and convert the whole thing to integer

        ebas_qc_var = self.get_ebas_data_qc_variable(tmp_data, _data_var)
        flags = tmp_data[ebas_qc_var].values
        # remove NaNs and set them to EBAS_FLAG_NAN_NUMBER
        flags[np.isnan(flags)] = EBAS_FLAG_NAN_NUMBER

        return flags.astype(int)

    def get_ebas_var_names_with_std_names(self, tmp_data, std_names):
        """small helper method to find variable names that match a certain std_names"""
        ret_list = []
        for d_idx, _data_var in enumerate(
            self._get_ebas_data_vars(
                tmp_data,
            )
        ):
            var_std_name = self.get_ebas_data_standard_name(tmp_data, _data_var)
            if var_std_name in std_names:
                ret_list.append(_data_var)
            if len(ret_list) == 0:
                # This shouldn't happen
                raise ActrisEbasStdNameNotFoundException(_data_var)
        return ret_list

    def get_var_data_flags_applied_from_vars(self, vals, ebas_flags):
        """helper method to get the data variable with flags"""
        # vals = tmp_data[_data_var].values
        # apply flags

        # ebas_flags = self.get_ebas_var_flags(tmp_data, _data_var)
        ts_no = len(vals)
        # quick test if we need to apply flags at all
        if np.nansum(ebas_flags) == ebas_flags.size * EBAS_FLAG_NAN_NUMBER:
            flags = np.full(ts_no, Flag.VALID, dtype="i2")
        else:
            flags = np.full(ts_no, Flag.INVALID, dtype="i2")
            # ebas_flags can be one or multidimensional...
            if len(ebas_flags.shape) > 1:
                for _ebas_flag in ebas_flags:
                    for f_idx, flag in enumerate(_ebas_flag):
                        if (flag == 0) or (flag in self.ebas_valid_flags):
                            flags[f_idx] = Flag.VALID
            else:
                for f_idx, flag in enumerate(ebas_flags):
                    if (flag == 0) or (flag in self.ebas_valid_flags):
                        flags[f_idx] = Flag.VALID

        return vals, flags

    def get_var_data_flags_applied_from_file(self, tmp_data, _data_var):
        """helper method to get the data variable with flags"""
        vals = tmp_data[_data_var].values
        # apply flags

        ebas_flags = self.get_ebas_var_flags(tmp_data, _data_var)
        return self.get_var_data_flags_applied_from_vars(vals, ebas_flags)

    def calc_var(self, tmp_data, _data_var, _var):
        """helper method to calculate compound variables like depositions"""

        # for the moment this will just multiply 2 variables within the same file

        if "standard_names_2nd_var" in self.def_data["variables"][_var]:
            var_names_to_check = self.get_ebas_var_names_with_std_names(
                tmp_data, self.def_data["variables"][_var]["standard_names_2nd_var"]
            )
            if len(var_names_to_check) > 1:
                logger.info(
                    f"calc_var: more than one matching variable name found for std_names {self.def_data['variables'][_var]}. Using the 1st match. "
                )
            vals1, flags1 = self.get_var_data_flags_applied_from_file(
                tmp_data, _data_var
            )
            vals2, flags2 = self.get_var_data_flags_applied_from_file(
                tmp_data, var_names_to_check[0]
            )

            vals = vals1 * vals2
            units = self.def_data["variables"][_var]["units"]
            # unifying flags from 2 variables might be a bit problematic, but in principle they should be the same anyway
            # just return the flags from the precipitation here for now

            return vals, flags2, units
        else:
            raise ActrisEbasStdNameNotFoundException

    def get_ebas_valid_flags(self, url: str = EBAS_FLAG_URL) -> dict:
        """small helper to download the ebas flag file from NILU"""

        df = polars.read_csv(url)
        idx_arr = np.where(df[df.columns[-1]].to_numpy() == "V")
        ret_data = df[df.columns[0]].to_numpy()[idx_arr]

        return ret_data

    def get_ebas_data_units(self, tmp_data, var_name, url):
        """small helper method to get the ebas unit from the data file"""
        unit = tmp_data[var_name].attrs["units"]
        ebas_unit = tmp_data[var_name].attrs["ebas_unit"]
        if unit != ebas_unit:
            logger.error(
                f"Error: mismatch between units {unit} and ebas_unit {ebas_unit} attributes for URL {url}"
            )
        try:
            return CF_UNITS[ebas_unit]
        except KeyError:
            logger.info(f"No CF unit found for {ebas_unit}. Please add if needed.")
            return ebas_unit

    def get_ebas_data_standard_name(self, tmp_data, var_name):
        """small helper method to get the ebas standard_name for a given variable from the data file"""
        ret_data = ""
        try:
            ret_data = tmp_data[var_name].attrs["standard_name"]
        except KeyError:
            pass
        # remove blanks just to be sure
        return ret_data.replace(" ", "")

    def get_ebas_data_ancillary_variables(self, tmp_data, var_name):
        """
        small helper method to get the ebas ancillary variables from the data file
        These contain the data flags (hopefully always ending with "_qc" and additional metedata
        (hopefully always ending with "_ebasmetadata" for each time step
        """
        ret_data = tmp_data[var_name].attrs["ancillary_variables"].split()
        return ret_data

    def get_ebas_data_qc_variable(self, tmp_data, var_name):
        """
        small helper method to get the ebas quality control variable name
        for a given variable name in the ebas data file
        uses self.get_ebas_data_ancillary_variables to get the variable names of the
        ancillary variables
        """
        ret_data = None
        # try using the ancillary variables attribute to find the flag variable
        for var in self.get_ebas_data_ancillary_variables(tmp_data, var_name):
            for time_name in TIME_VAR_NAME:
                if time_name in tmp_data[var_name].dims and var in tmp_data.variables:
                    return var
                else:
                    logger.info(
                        f"getting ancillary_variables from 'ancillary_variables' attribute failed for variable {var_name}. Trying fall back way..."
                    )

        # try just adding "_qc" to the variable name
        if ret_data is None:
            if var_name + "_qc" in tmp_data.variables:
                return var_name + "_qc"
            else:
                raise ActrisEbasQcVariableNotFoundException(
                    f"Error: no flag data for variable {var_name} found!"
                )
        return ""

    def get_ebas_data_country_code(self, tmp_data):
        """small helper method to get the ebas country code from the data file"""
        return tmp_data.attrs["ebas_station_code"][0:2]

    def get_actris_standard_name(self, actris_var_name):
        """small helper method to get corresponding CF standard name for a given ACTRIS variable"""
        try:
            return self.def_data[STD_NAME_SECTION_NAME][actris_var_name]
        except KeyError:
            raise ActrisEbasStdNameNotFoundException(
                f"Error: no CF standard name for {actris_var_name} found!"
            )

    def get_ebas_standard_name(self, ebas_var_name):
        """small helper method to get corresponding CF standard name for a given EBAS variable"""
        try:
            return self.def_data[EBAS_VAR_SECTION_NAME][ebas_var_name]["standard_names"]
        except KeyError:
            raise ActrisEbasStdNameNotFoundException(
                f"Error: no CF standard name for {ebas_var_name} found!"
            )

    def _get_ebas_data_vars(self, tmp_data, actris_var: str = None, units: str = None):
        """
        small helper method to isolate potential data variables
        since the variable names have no meaning (even if it seems otherwise)

        Selects potential data variables based on which dimension they depend on
        Data variables depend on the time dimension only
        """

        data_vars = []
        for data_var in tmp_data.data_vars:
            if len(tmp_data[data_var].dims) != 1:
                continue
            elif tmp_data[data_var].dims[0] in TIME_VAR_NAME:
                try:
                    cell_methods = tmp_data[data_var].attrs["cell_methods"]
                except KeyError:
                    cell_methods = None
                try:
                    units = tmp_data[data_var].attrs["units"]
                except KeyError:
                    units = None
                if cell_methods is None and units is None:
                    # old data, just copy
                    data_vars.append(data_var)
                elif cell_methods is not None:
                    if cell_methods in CELL_METHODS_TO_COPY:
                        data_vars.append(data_var)
                else:
                    pass

        return data_vars

    def extract_opendap_info(
        self,
        json_resp: dict,
        sites_to_read: list[str] = [],
        sites_to_exclude: list[str] = [],
    ) -> dict:
        """
        small helper method to extract opendap URLs to download from json reponse from the EBAS API
        """
        opendap_urls_to_dl = {}
        # highest hierachy is a list
        for site_idx, site_data in enumerate(json_resp):
            site_name = site_data[LOCATION_ROOT_KEY][LOCATION_FACILITY_KEY][
                LOCATION_NAME_KEY
            ]
            product_type = site_data[PRODUCT_TYPE_ROOT_KEY][PRODUCT_TYPE_KEY]
            logger.info(f"product type station {site_name}: {product_type}")
            if product_type not in PRODUCT_TYPES_TO_COPY:
                logger.info(f"station {site_name} skipping product type {product_type}")
                continue

            if site_name in sites_to_exclude:
                logger.info(f"site {site_name} excluded due to exclusion filter")
                continue
            if site_name in sites_to_read or len(sites_to_read) == 0:
                if site_name not in opendap_urls_to_dl:
                    opendap_urls_to_dl[site_name] = []

                # site_data[DISTRIBUTION_ROOT_KEY] is also a list
                # search for protocol DISTRIBUTION_PROTOCOL_NAME
                for url_idx, distribution_data in enumerate(
                    site_data[DISTRIBUTION_ROOT_KEY]
                ):
                    if (
                        distribution_data[DISTRIBUTION_PROTOCOL_KEY].lower()
                        != DISTRIBUTION_PROTOCOL_NAME_OPENDAP
                    ):
                        logger.info(
                            f"skipping site: {site_name} / proto: {distribution_data[DISTRIBUTION_PROTOCOL_KEY]}"
                        )
                        continue
                    else:
                        url = distribution_data[DISTRIBUTION_URL_KEY]
                        opendap_urls_to_dl[site_name].append(url)
                        logger.info(
                            f"site: {site_name} / proto: {distribution_data[DISTRIBUTION_PROTOCOL_KEY]} included in URL list"
                        )
                        if url not in self.time_coverages:
                            time_dummy = (
                                site_data[TIME_COVERAGE_ROOT_KEY][
                                    TIME_COVERAGE_START_KEY
                                ],
                                site_data[TIME_COVERAGE_ROOT_KEY][
                                    TIME_COVERAGE_END_KEY
                                ],
                            )
                            # check for time zone info in the time coverage string (times should be in UTC)
                            if (
                                len(
                                    site_data[TIME_COVERAGE_ROOT_KEY][
                                        TIME_COVERAGE_START_KEY
                                    ]
                                )
                                > 19
                                or len(
                                    site_data[TIME_COVERAGE_ROOT_KEY][
                                        TIME_COVERAGE_END_KEY
                                    ]
                                )
                                > 19
                            ):
                                logger.info(
                                    f"Non UTC time coverage string {time_dummy} in API response for URL {url}. Please check for errors. Removing TZ info for speed"
                                )
                                time_dummy = (
                                    site_data[TIME_COVERAGE_ROOT_KEY][
                                        TIME_COVERAGE_START_KEY
                                    ][0:19],
                                    np.datetime64(
                                        site_data[TIME_COVERAGE_ROOT_KEY][
                                            TIME_COVERAGE_END_KEY
                                        ][0:19]
                                    ),
                                )
                                self.time_coverages[url] = (
                                    np.datetime64(time_dummy[0]),
                                    np.datetime64(time_dummy[1]),
                                )
                            else:
                                self.time_coverages[url] = (
                                    np.datetime64(
                                        site_data[TIME_COVERAGE_ROOT_KEY][
                                            TIME_COVERAGE_START_KEY
                                        ]
                                    ),
                                    np.datetime64(
                                        site_data[TIME_COVERAGE_ROOT_KEY][
                                            TIME_COVERAGE_END_KEY
                                        ]
                                    ),
                                )
                        else:
                            logger.info(
                                f"Error: URL {url} already included in site used for a 2nd station!"
                            )
                        break
        return opendap_urls_to_dl

    def extract_dl_url_info(
        self,
        json_resp: dict,
        sites_to_read: list[str] = [],
        sites_to_exclude: list[str] = [],
    ) -> dict:
        """
        small helper method to extract download URLs to download from json reponse from the EBAS API
        These files need to be read using the http protocol
        Separate method from the opendap url extraction because it's not used at the moment but
        might be needed in future
        """
        urls_to_dl = {}
        # highest hierarchy is a list
        for site_idx, site_data in enumerate(json_resp):
            site_name = site_data[LOCATION_ROOT_KEY][LOCATION_FACILITY_KEY][
                LOCATION_NAME_KEY
            ]
            product_type = site_data[PRODUCT_TYPE_ROOT_KEY][PRODUCT_TYPE_KEY]
            logger.info(f"DL: product type station {site_name}: {product_type}")
            if product_type not in PRODUCT_TYPES_TO_COPY:
                logger.info(
                    f"DL: station {site_name} skipping product type {product_type}"
                )
                continue

            if site_name in sites_to_exclude:
                logger.info(f"DL: site {site_name} excluded due to exclusion filter")
                continue
            if site_name in sites_to_read or len(sites_to_read) == 0:
                if site_name not in urls_to_dl:
                    urls_to_dl[site_name] = []

                # site_data[DISTRIBUTION_ROOT_KEY] is also a list
                # search for protocol DISTRIBUTION_PROTOCOL_NAME
                for url_idx, distribution_data in enumerate(
                    site_data[DISTRIBUTION_ROOT_KEY]
                ):
                    if (
                        distribution_data[DISTRIBUTION_PROTOCOL_KEY].lower()
                        != DISTRIBUTION_PROTOCOL_NAME_HTTP
                    ):
                        logger.info(
                            f"DL: skipping site: {site_name} / proto: {distribution_data[DISTRIBUTION_PROTOCOL_KEY]}"
                        )
                        continue
                    else:
                        url = distribution_data[DISTRIBUTION_URL_KEY]
                        urls_to_dl[site_name].append(url)
                        logger.info(
                            f"DL: site: {site_name} / proto: {distribution_data[DISTRIBUTION_PROTOCOL_KEY]} included in URL list"
                        )
                        if url not in self.time_coverages:
                            self.time_coverages[url] = (
                                np.datetime64(
                                    site_data[TIME_COVERAGE_ROOT_KEY][
                                        TIME_COVERAGE_START_KEY
                                    ]
                                ),
                                np.datetime64(
                                    site_data[TIME_COVERAGE_ROOT_KEY][
                                        TIME_COVERAGE_END_KEY
                                    ]
                                ),
                            )
                        else:
                            logger.info(
                                f"Error: dl URL {url} already included in site used for a 2nd station!"
                            )
                        break
        return urls_to_dl

    def _unfiltered_data(self, varname) -> Data:
        self._read()
        return self._data[varname]

    def _unfiltered_stations(self) -> dict[str, Station]:
        self._read()
        return self._stations

    def _unfiltered_variables(self) -> list[str]:
        self._read()
        return list(self._data.keys())

    def close(self):
        pass

    def _read_definitions(self, file=DEFINITION_FILE):
        # definitions file for a connection between aerocom names, ACTRIS vocabulary and EBAS vocabulary
        # The EBAS part will hopefully not be necessary in the next EBAS version anymore
        with open(file, "rb") as fh:
            tmp = tomllib.load(fh)
        return tmp

    def is_valid_url(self, url):
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False


class ActrisEbasTimeSeriesEngine(AutoFilterReaderEngine.AutoFilterEngine):
    def reader_class(self) -> AutoFilterReaderEngine:
        return ActrisEbasTimeSeriesReader

    def open(self, url, *args, **kwargs) -> Reader:
        return self.reader_class()(url, *args, **kwargs)

    def description(self) -> str:
        return "ACTRIS EBAS reader using the pyaro infrastructure"

    def url(self) -> str:
        return "https://github.com/metno/pyaro-readers"
