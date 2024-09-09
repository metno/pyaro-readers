import logging
import tomllib
from io import BytesIO
from urllib.parse import urlparse, quote
from urllib.request import urlopen

from urllib3.util.retry import Retry
from urllib3.poolmanager import PoolManager

import numpy as np
import requests
import json
from pyaro.timeseries import (
    AutoFilterReaderEngine,
    Data,
    Flag,
    NpStructuredData,
    Station,
)
from tqdm import tqdm
import datetime
import xarray as xr
import os

logger = logging.getLogger(__name__)

# default API URL base
# BASE_API_URL = "https://prod-actris-md.nilu.no/Vocabulary/categories"
BASE_API_URL = "https://prod-actris-md.nilu.no/"
# base URL to query for data for a certain variable
VAR_QUERY_URL = f"{BASE_API_URL}Metadata/content/"
# basename of definitions.toml which connects the pyaerocom variable names with the ACTRIS variable names
DEFINITION_FILE_BASENAME = "definitions.toml"

DEFINITION_FILE = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), DEFINITION_FILE_BASENAME
)

# number of times an api  request is tried before we consider it failed
MAX_RETRIES = 2

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


class ActrisEbasTestDataNotFoundException(Exception):
    pass


class ActrisEbasTimeSeriesReader(AutoFilterReaderEngine.AutoFilterReader):
    def __init__(
            self,
            filters=[],
            tqdm_desc: str | None = None,
            ts_type: str = "daily",
            test_flag: bool = True,
    ):
        """ """
        self._filename = None
        self._stations = {}
        self._urls_to_dl = {}
        self._data = {}  # var -> {data-array}
        self._set_filters(filters)
        self._header = []
        self._metadata = {}
        _laststatstr = ""
        self._revision = datetime.datetime.min
        self._metadata["revision"] = datetime.datetime.strftime(
            self._revision, "%y%m%d%H%M%S"
        )

        try:
            vars_to_read = filters["variables"]["include"]
        except KeyError:
            raise ValueError(
                f"As of now, you have to give the species you want to read in filter.variables.include"
            )

        try:
            sites_to_read = filters["stations"]["include"]
        except KeyError:
            sites_to_read = []

        try:
            sites_to_exclude = filters["stations"]["exclude"]
        except KeyError:
            sites_to_exclude = []

        # read config file
        self._def_data = self._read_definitions(file=DEFINITION_FILE)
        for var in vars_to_read:
            self._metadata[var] = {}
            # for testing since the API is error-prone and slow at the time of this writing
            test_file = os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                f"{var}.json",
            )
            if os.path.exists(test_file) and test_flag:
                with open(test_file, "r") as f:
                    json_resp = json.load(f)
            else:
                # search for variable metadata
                query_url = f"{VAR_QUERY_URL}{quote(var)}"
                retries = Retry(connect=5, read=2, redirect=5)
                http = PoolManager(retries=retries)
                response = http.request("GET", query_url)

                json_resp = json.loads(response.data.decode("utf-8"))

            self._metadata[var] = json_resp
            self._urls_to_dl[var] = self.extract_urls(
                json_resp,
                sites_to_read=sites_to_read,
                sites_to_exclude=sites_to_exclude,
            )
            self._data[var] = self.read_data(self._urls_to_dl[var])

    def metadata(self):
        return self._metadata

    def read_data(
            self,
            urls_to_dl: dict,
            tqdm_desc="reading stations",
            sites_to_read: list[str] = None,
    ):
        """
        read the data from EBAS thredds server
        """
        bar = tqdm(desc=tqdm_desc, total=len(urls_to_dl))
        for s_idx, site_name in enumerate(urls_to_dl):
            for f_idx, url in enumerate(urls_to_dl[site_name]):
                tmp_data = xr.open_dataset(url)
                # create times...
                start_time = np.asarray(tmp_data["time_bnds"][:, 0])
                stop_time = np.asarray(tmp_data["time_bnds"][:, 1])
                ts_no = len(start_time)
                lat = np.full(ts_no, tmp_data.attrs["geospatial_lat_min"])
                lon = np.full(ts_no, tmp_data.attrs["geospatial_lon_min"])
                station = np.full(ts_no, tmp_data.attrs["ebas_station_name"])
                altitude = np.full(ts_no, tmp_data.attrs["geospatial_vertical_min"])
                standard_deviation = np.full(ts_no, np.nan)

                # put all data variables in the data struct for the moment
                for _data_var in self._get_ebas_data_vars(tmp_data):
                    vals = tmp_data[_data_var].values
                    flags = np.full(ts_no, Flag.VALID)
                    if _data_var not in self._data:
                        self._data[_data_var] = NpStructuredData(
                            _data_var, self.get_ebas_data_units(tmp_data, _data_var)
                        )

                    self._data[_data_var].append(
                        value=vals,
                        station=station,
                        latitude=lat,
                        longitude=lon,
                        altitude=altitude,
                        start_time=start_time,
                        end_time=stop_time,
                        # TODO: Currently assuming that all observations are valid.
                        flag=flags,
                        standard_deviation=standard_deviation,
                    )
            if not site_name in self._stations:
                self._stations[site_name] = Station(
                    {
                        "station": site_name,
                        "longitude": lon[0],
                        "latitude": lat[0],
                        "altitude": altitude[0],
                        "country": self.get_ebas_data_country_code(tmp_data),
                        "url": "",
                        "long_name": site_name,
                    }
                )
            bar.update(1)
        bar.close()

    def get_ebas_data_units(self, tmp_data, var_name):
        """small helper method to get the ebas unit from the data file"""
        unit = tmp_data[var_name].attrs["units"]
        return unit

    def get_ebas_data_country_code(self, tmp_data):
        """small helper method to get the ebas country code from the data file"""
        return tmp_data.attrs["ebas_station_code"][0:2]

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
                data_vars.append(data_var)

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
                        continue
                    else:
                        urls_to_dl[site_name].append(
                            distribution_data[DISTRIBUTION_URL_KEY]
                        )
                        break
        return urls_to_dl

    def _unfiltered_data(self, varname) -> Data:
        return self._data[varname]

    def _unfiltered_stations(self) -> dict[str, Station]:
        return self._stations

    def _unfiltered_variables(self) -> list[str]:
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
    def reader_class(self):
        return ActrisEbasTimeSeriesReader

    # def open(self, filename, *args, **kwargs) -> ActrisEbasTimeSeriesReader:
    def open(self, *args, **kwargs) -> ActrisEbasTimeSeriesReader:
        # return self.reader_class()(filename, *args, **kwargs)
        return self.reader_class()(*args, **kwargs)

    def description(self):
        return "ACTRIS EBAS reader using the pyaro infrastructure"

    def url(self):
        return "https://github.com/metno/pyaro-readers"
