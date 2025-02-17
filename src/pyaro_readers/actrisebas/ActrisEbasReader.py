import datetime
import json
import logging
import numpy as np
import os
import polars
import tomllib
import xarray as xr
from tqdm import tqdm
from urllib.parse import urlparse, quote
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
# BASE_API_URL = "https://dev-actris-md.nilu.no/"
# BASE_API_URL = "https://prod-actris-md.nilu.no/"
BASE_API_URL = "https://dev-actris-md2.nilu.no/"
# base URL to query for data for a certain variable
VAR_QUERY_URL = f"{BASE_API_URL}metadata/content/"
# basename of definitions.toml which connects the pyaerocom variable names with the ACTRIS variable names
DEFINITION_FILE_BASENAME = "definitions.toml"
# online ressource of ebas flags
EBAS_FLAG_URL = "https://folk.nilu.no/~ebas/EBAS_Masterdata/ebas_flags.csv"

DEFINITION_FILE = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), DEFINITION_FILE_BASENAME
)
EBAS_FLAGS_FILE = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "ebas_flags.csv"
)

# name of the standard_name section in the DEFINITION_FILE
STD_NAME_SECTION_NAME = "actris_standard_names"

# name of the ebas section in the DEFINITION_FILE
EBAS_VAR_SECTION_NAME = "variables"

#
CELL_METHODS_TO_COPY = [
    "time: mean",
    "time: median",

]


# number of times an api  request is tried before we consider it failed
MAX_RETRIES = 2

# number used instead of NaN in flags
# in the netcdf files there's actually a zero, but there's also a _FillValue attribute that sets that to NaN again
EBAS_FLAG_NAN_NUMBER = 0

# name of the root key containing the download information
DISTRIBUTION_ROOT_KEY = "md_distribution_information"
DISTRIBUTION_PROTOCOL_KEY = "protocol"
DISTRIBUTION_PROTOCOL_NAME = "OPeNDAP"
DISTRIBUTION_URL_KEY = "dataset_url"

# some info to get to station name and location
LOCATION_ROOT_KEY = "md_data_identification"
LOCATION_FACILITY_KEY = "facility"
LOCATION_NAME_KEY = "name"
LOCATION_LAT_KEY = "lat"
LOCATION_LON_KEY = "lon"
LOCATION_ALT_KEY = "alt"

# name of netcdf time variable in the netcdf files
# should be "time" as of CF convention, but other names can be added here
TIME_VAR_NAME = ["time"]


class ActrisEbasRetryException(Exception):
    pass


class ActrisEbasStdNameNotFoundException(Exception):
    pass


class ActrisEbasQcVariableNotFoundException(Exception):
    pass


class ActrisEbasTestDataNotFoundException(Exception):
    pass

class ActrisEbasWrongCellMethodOrUnitException(Exception):
    pass


class ActrisEbasTimeSeriesReader(AutoFilterReaderEngine.AutoFilterReader):
    def __init__(
        self,
        filename_or_obj_or_url=BASE_API_URL,
        filters=[],
        # tqdm_desc: str | None = None,
        # ts_type: str = "daily",
        test_flag: bool = False,
    ):
        """ """
        self._filename = None
        # if isinstance(vars_to_read, str):
        #     self.vars_to_read = [vars_to_read]
        # else:
        #     self.vars_to_read = vars_to_read
        self._stations = {}
        self.urls_to_dl = {}
        self._data = {}  # var -> {data-array}
        self._set_filters(filters)
        # self._header = []
        self._metadata = {}
        # used for variable matching in the EBAS data files
        # gives a mapping between the EBAS or pyaerocom variable name
        # and the CF standard name found in the EBAS data files
        # Due to standard_names aliases, the values are a list
        self.standard_names = {}
        # _laststatstr = ""
        self._revision = datetime.datetime.now()
        self._metadata["revision"] = datetime.datetime.strftime(
            self._revision, "%y%m%d%H%M%S"
        )
        self.ebas_valid_flags = self.get_ebas_valid_flags()
        self.sites_to_read = None
        self.vars_to_read = None
        self.times_to_read = (np.datetime64(1, "Y"), np.datetime64(120, "Y"))

        # set filters
        for filter in filters:
            if isinstance(filter, Filter.StationFilter):
                self.sites_to_read = filter.init_kwargs()["include"]
                self.sites_to_exclude = filter.init_kwargs()["exclude"]
            elif isinstance(filter, Filter.VariableNameFilter):
                self.vars_to_read = filter.init_kwargs()["include"]
                logger.info(f"applying variable include filter {self.vars_to_read}...")
            elif isinstance(filter, Filter.TimeBoundsFilter):
                # this is not the full implementation. Correct filtering will be done
                # by pyaro
                # self.self.times_to_read = filter.init_kwargs()["start_include"]
                # not the most pythonic way to do this...
                self.times_to_read = (
                    np.min(filter._start_include),
                    np.max(filter._start_include),
                )
                logger.info(f"applying time include filter {self.times_to_read}...")
            else:
                # pass on not reader supported filters
                pass
            # for time filter:
            # There's time_coverage_start and time_coverage_end in the global attributes with the
            # time coverage as ISO string
            # just looking at the time variable is not enough. It notes the middle time. The time_bnds variable
            # has to be applied as well
            # np.datetime64(tmp_data.attrs["time_coverage_start"].split()[0])
            # np.datetime64(tmp_data.attrs["time_coverage_end"].split()[0])

        if self.vars_to_read is None:
            logger.info(f"No variable filter given, nothing to read...")
            self.vars_to_read = []

        # read config file
        self.def_data = self._read_definitions(file=DEFINITION_FILE)
        # Because the user might have given a pyaerocom name, build self.actris_vars_to_read with a list
        # of ACTRIS variables to read. values are a list
        self.actris_vars_to_read = {}
        for var in self.vars_to_read:
            self._metadata[var] = {}
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
                        self.standard_names[_actris_var] = self.get_ebas_standard_name(var)
                    except KeyError:
                        logger.info(f"No ebas standard names found for {var}. Trying those of the actris variable {self.actris_vars_to_read[var][0]} instead...")
                        self.standard_names[_actris_var] = self.get_actris_standard_name(_actris_var)
                # for _actris_var in self.actris_vars_to_read[var]:
                #     try:
                #         self.standard_names[var].extend(
                #             self.get_actris_standard_name(_actris_var)
                #         )
                #         self.standard_names[_actris_var].extend(
                #             self.get_actris_standard_name(_actris_var)
                #         )
                #     except KeyError:
                #         self.standard_names[var] = self.get_actris_standard_name(
                #             _actris_var
                #         )
                #         self.standard_names[_actris_var] = (
                #             self.get_actris_standard_name(_actris_var)
                #         )

            else:
                # user gave ACTRIS name
                self.actris_vars_to_read[var].append(var)
                self.standard_names[var] = self.get_actris_standard_name(var)

        for _pyaro_var in self.actris_vars_to_read:
            self._metadata[_pyaro_var] = {}
            for _actris_var in self.actris_vars_to_read[_pyaro_var]:
                # for testing since the API is error-prone and slow at the time of this writing
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

                self._metadata[_pyaro_var][_actris_var] = json_resp
                self.urls_to_dl[_actris_var] = self.extract_urls(
                    json_resp,
                    sites_to_read=self.sites_to_read,
                    sites_to_exclude=self.sites_to_exclude,
                )
                # The following needs some refinement once we read pyaerocom variables that hold more than
                # one EBAS variable
                # we need to decide per station which EBAS variable to return at a certain station and potentially time
                # self.read_data(
                #     actris_variable=_pyaro_var, urls_to_dl=self.urls_to_dl[_actris_var]
                # )
                assert self._metadata[_pyaro_var][_actris_var]
                # return _pyaro_var, self.urls_to_dl

    def metadata(self):
        return self._metadata

    def _read(
        self,
        tqdm_desc="reading stations",
    ):
        """
        read the data from EBAS thredds server
        """
        # for actris vocabulary key and value of self.actris_vars_to_read are the same
        # for pyaerocom vocabulary they are not (key is pyaerocom variable name there)!
        for _var in self.actris_vars_to_read:
            if _var in self._data:
                logger.info(f"var {_var} already read")
                continue
            for actris_variable in self.actris_vars_to_read[_var]:
                # actris_variable = self.actris_vars_to_read[_var][0]

                urls_to_dl = self.urls_to_dl[actris_variable]
                bar = tqdm(desc=tqdm_desc, total=len(urls_to_dl), disable=None)
                for s_idx, site_name in enumerate(urls_to_dl):
                    for f_idx, url in enumerate(urls_to_dl[site_name]):
                        logger.info(f"reading file {url}")
                        tmp_data = xr.open_dataset(url)
                        # check for time filter by looking into
                        # np.datetime64(tmp_data.attrs["time_coverage_start"].split()[0])
                        # and
                        # np.datetime64(tmp_data.attrs["time_coverage_end"].split()[0])
                        # We also could have a look at the time variable, but the obe saves some time calulations
                        # (applying the time bounds to the middle points in the time variable)
                        file_start_time = np.datetime64(
                            tmp_data.attrs["time_coverage_start"].split()[0]
                        )
                        file_end_time = np.datetime64(
                            tmp_data.attrs["time_coverage_end"].split()[0]
                        )
                        # if (file_start_time >= self.times_to_read[0] and file_start_time <= self.times_to_read[1]) \
                        #     or (file_end_time >= self.times_to_read[0] and file_end_time <= self.times_to_read[1]):
                        if (
                            file_end_time < self.times_to_read[0]
                            or file_start_time > self.times_to_read[1]
                        ):
                            logger.info(f"url {url} not read. Outside of time bounds.")
                            continue

                        # put all data variables in the data struct for the moment
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

                            # assert f"station {site_name}, file #{f_idx}: found matching standard_name {std_name}"
                            long_name = tmp_data.attrs["ebas_station_name"]
                            stat_code = tmp_data.attrs["ebas_station_code"]
                            # create variables valid for all measured variables...
                            start_time = np.asarray(tmp_data["time_bnds"][:, 0])
                            stop_time = np.asarray(tmp_data["time_bnds"][:, 1])
                            ts_no = len(start_time)
                            lat = np.full(ts_no, tmp_data.attrs["geospatial_lat_min"])
                            lon = np.full(ts_no, tmp_data.attrs["geospatial_lon_min"])
                            # station = np.full(ts_no, tmp_data.attrs["ebas_station_code"])
                            station = np.full(ts_no, long_name)
                            altitude = np.full(
                                ts_no, tmp_data.attrs["geospatial_vertical_min"]
                            )
                            standard_deviation = np.full(ts_no, np.nan)
                            vals = tmp_data[_data_var].values
                            # apply flags

                            ebas_flags = self.get_ebas_var_flags(tmp_data, _data_var)
                            # quick test if we need to apply flags at all
                            if (
                                np.nansum(ebas_flags)
                                == ebas_flags.size * EBAS_FLAG_NAN_NUMBER
                            ):
                                flags = np.full(ts_no, Flag.VALID, dtype="i2")
                            else:
                                flags = np.full(ts_no, Flag.INVALID, dtype="i2")
                                for _ebas_flag in ebas_flags:
                                    for f_idx, flag in enumerate(_ebas_flag):
                                        if (flag == 0) or (
                                            flag in self.ebas_valid_flags
                                        ):
                                            flags[f_idx] = Flag.VALID

                            if _var not in self._data:
                                self._data[_var] = NpStructuredData(
                                    _var,
                                    self.get_ebas_data_units(tmp_data, _data_var),
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
                            if not site_name in self._stations:
                                self._stations[site_name] = Station(
                                    {
                                        "station": stat_code,
                                        "longitude": lon[0],
                                        "latitude": lat[0],
                                        "altitude": altitude[0],
                                        "country": self.get_ebas_data_country_code(tmp_data),
                                        "url": "",
                                        # This is used by pyaerocom
                                        "long_name": site_name,
                                    }
                                )
                    bar.update(1)
                bar.close()
        assert True

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

    def get_ebas_valid_flags(self, url: str = EBAS_FLAG_URL) -> dict:
        """small helper to download the bas flag file from NILU"""

        df = polars.read_csv(url)
        idx_arr = np.where(df[df.columns[-1]].to_numpy() == "V")
        ret_data = df[df.columns[0]].to_numpy()[idx_arr]
        # return this as a python dict for now
        # ret_data = {}
        # for var in df.columns:
        #     ret_data[var] = df[var].to_list()
        #
        # # for simplicity add a dict entry listing the valid flags
        # # last column is the explanation ("V" for valid)
        # ret_data["valid"] = ret_data["Flag"][var == "V"]

        return ret_data

    # decoded_content = download.content.decode('utf-8')
    def get_ebas_data_units(self, tmp_data, var_name):
        """small helper method to get the ebas unit from the data file"""
        unit = tmp_data[var_name].attrs["units"]
        return unit

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
                # elif cell_methods is not None and units is not None:
                #     if cell_methods in CELL_METHODS_TO_COPY and units == self.def_data["actris_std_units"][data_var]:
                #         data_vars.append(data_var)
                elif cell_methods is not None:
                        if cell_methods in CELL_METHODS_TO_COPY:
                            data_vars.append(data_var)
                # elif units is not None:
                #     if units == self.def_data["actris_std_units"][data_var]:
                #         data_vars.append(data_var)
                else:
                    pass

        return data_vars

    def extract_urls(
        self,
        json_resp: dict,
        sites_to_read: list[str] = [],
        sites_to_exclude: list[str] = [],
    ) -> dict:
        """
        small helper method to extract URLs to download from json reponse from the EBAS API
        """
        urls_to_dl = {}
        # highest hierachy is a list
        for site_idx, site_data in enumerate(json_resp):
            site_name = site_data[LOCATION_ROOT_KEY][LOCATION_FACILITY_KEY][
                LOCATION_NAME_KEY
            ]
            if site_name in sites_to_exclude:
                logger.info(f"site {site_name} excluded due to exclusion filter")
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
                        distribution_data[DISTRIBUTION_PROTOCOL_KEY]
                        != DISTRIBUTION_PROTOCOL_NAME
                    ):
                        logger.info(
                            f"skipping site: {site_name} / proto: {distribution_data[DISTRIBUTION_PROTOCOL_KEY]}"
                        )
                        continue
                    else:
                        urls_to_dl[site_name].append(
                            distribution_data[DISTRIBUTION_URL_KEY]
                        )
                        logger.info(
                            f"site: {site_name} / proto: {distribution_data[DISTRIBUTION_PROTOCOL_KEY]} included in URL list"
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
