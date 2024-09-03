import logging
import tomllib
from io import BytesIO
from urllib.parse import urlparse
from urllib.request import urlopen

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
VAR_QUERY_URL = f"{BASE_API_URL}/content/"
# basename of definitions.toml which connects the pyaerocom variable names with the ACTRIS variable names
DEFINITION_FILE_BASENAME = "definitions.toml"

DEFINITION_FILE = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    DEFINITION_FILE_BASENAME)

class ActrisEbasTimeSeriesReader(AutoFilterReaderEngine.AutoFilterReader):
    def __init__(
        self,
        filename,
        filters=[],
            var_name="ozone mass concentration",
        tqdm_desc: str | None = None,
        ts_type: str = "daily",
    ):
        """
        """
        self._filename = filename
        self._stations = {}
        self._data = {}  # var -> {data-array}
        self._set_filters(filters)
        self._header = []
        _laststatstr = ""
        self._revision = datetime.datetime.min
        # read config file
        self._def_data = self._read_definitions(file=DEFINITION_FILE)

        # bar = tqdm(desc=tqdm_desc, total=len(lines))
        # bar.close()

    def metadata(self):
        return dict(revision=datetime.datetime.strftime(self._revision, "%y%m%d%H%M%S"))

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
        with open(file, 'rb') as fh:
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

    def open(self, filename, *args, **kwargs) -> ActrisEbasTimeSeriesReader:
        return self.reader_class()(filename, *args, **kwargs)

    def description(self):
        return "ACTRIS EBAS reader using the pyaro infrastructure"

    def url(self):
        return "https://github.com/metno/pyaro-readers"
