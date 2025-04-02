import csv
import datetime
from io import BytesIO
from urllib.parse import urlparse
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile

import numpy as np
import requests
from geocoder_reverse_natural_earth import (
    Geocoder_Reverse_NE,
    Geocoder_Reverse_Exception,
)
from tqdm import tqdm

from pyaro.timeseries import (
    AutoFilterReaderEngine,
    Data,
    Flag,
    NpStructuredData,
    Station,
)

# default URL
BASE_URL = "https://aeronet.gsfc.nasa.gov/data_push/V3/All_Sites_Times_Daily_Averages_AOD20.zip"
# number of lines to read before the reading is handed to Pythobn's csv reader
HEADER_LINE_NO = 7
DELIMITER = ","
#
NAN_VAL = -999.0
# update progress bar every N lines...
PG_UPDATE_LINES = 100
# main variables to store
LAT_NAME = "Site_Latitude(Degrees)"
LON_NAME = "Site_Longitude(Degrees)"
ALT_NAME = "Site_Elevation(m)"
SITE_NAME = "AERONET_Site_Name"
DATE_NAME = "Date(dd:mm:yyyy)"
TIME_NAME: str = "Time(hh:mm:ss)"
AOD500_NAME = "AOD_500nm"
ANG4487_NAME = "440-870_Angstrom_Exponent"
AOD440_NAME = "AOD_440nm"
AOD870_NAME = "AOD_870nm"
AOD550_NAME = "AOD_550nm"

DATA_VARS = [AOD500_NAME, ANG4487_NAME, AOD440_NAME, AOD870_NAME]
COMPUTED_VARS = [AOD550_NAME]
# The computed variables have to be named after the read ones, otherwise the calculation will fail!
DATA_VARS.extend(COMPUTED_VARS)

FILL_COUNTRY_FLAG = True

TS_TYPE_DIFFS = {
    "daily": np.timedelta64(12, "h"),
    "instantaneous": np.timedelta64(0, "s"),
    "points": np.timedelta64(0, "s"),
    "monthly": np.timedelta64(15, "D"),
}


class AeronetSunTimeseriesReader(AutoFilterReaderEngine.AutoFilterReader):
    def __init__(
        self,
        filename,
        filters=[],
        fill_country_flag: bool = FILL_COUNTRY_FLAG,
        tqdm_desc: str | None = None,
        ts_type: str = "daily",
    ):
        """open a new Aeronet timeseries-reader

                :param filename: str
                :param filters:
                :param fill_country_flag:
                :param tqdm_desc:
                :param filename_or_obj_or_url: path-like object to csv-file

                input file looks like this (daily file; times noted are middle times):
        AERONET Version 3;
        Cuiaba
        Version 3: AOD Level 2.0
        The following data are automatically cloud cleared and quality assured with pre-field and post-field calibration applied.
        Contact: PI=Pawan Gupta and Elena Lind; PI Email=Pawan.Gupta@nasa.gov and Elena.Lind@nasa.gov
        Daily Averages,UNITS can be found at,,, https://aeronet.gsfc.nasa.gov/new_web/units.html
        AERONET_Site,Date(dd:mm:yyyy),Time(hh:mm:ss),Day_of_Year,AOD_1640nm,AOD_1020nm,AOD_870nm,AOD_865nm,AOD_779nm,AOD_675nm,AOD_667nm,AOD_620nm,AOD_560nm,AOD_555nm,AOD_551nm,AOD_532nm,AOD_531nm,AOD_510nm,AOD_500nm,AOD_490nm,AOD_443nm,AOD_440nm,AOD_412nm,AOD_400nm,AOD_380nm,AOD_340nm,Precipitable_Water(cm),AOD_681nm,AOD_709nm,AOD_Empty,AOD_Empty,AOD_Empty,AOD_Empty,AOD_Empty,440-870_Angstrom_Exponent,380-500_Angstrom_Exponent,440-675_Angstrom_Exponent,500-870_Angstrom_Exponent,340-440_Angstrom_Exponent,440-675_Angstrom_Exponent[Polar],N[AOD_1640nm],N[AOD_1020nm],N[AOD_870nm],N[AOD_865nm],N[AOD_779nm],N[AOD_675nm],N[AOD_667nm],N[AOD_620nm],N[AOD_560nm],N[AOD_555nm],N[AOD_551nm],N[AOD_532nm],N[AOD_531nm],N[AOD_510nm],N[AOD_500nm],N[AOD_490nm],N[AOD_443nm],N[AOD_440nm],N[AOD_412nm],N[AOD_400nm],N[AOD_380nm],N[AOD_340nm],N[Precipitable_Water(cm)],N[AOD_681nm],N[AOD_709nm],N[AOD_Empty],N[AOD_Empty],N[AOD_Empty],N[AOD_Empty],N[AOD_Empty],N[440-870_Angstrom_Exponent],N[380-500_Angstrom_Exponent],N[440-675_Angstrom_Exponent],N[500-870_Angstrom_Exponent],N[340-440_Angstrom_Exponent],N[440-675_Angstrom_Exponent[Polar]],Data_Quality_Level,AERONET_Instrument_Number,AERONET_Site_Name,Site_Latitude(Degrees),Site_Longitude(Degrees),Site_Elevation(m)
        Cuiaba,16:06:1993,12:00:00,167,-999.,0.081800,0.088421,-999.,-999.,0.095266,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,0.117581,-999.,-999.,-999.,0.149887,2.487799,-999.,-999.,-999.,-999.,-999.,-999.,-999.,0.424234,-999.,0.497630,-999.,0.924333,-999.,0,3,3,0,0,3,0,0,0,0,0,0,0,0,0,0,0,3,0,0,0,3,6,0,0,0,0,0,0,0,3,0,3,0,3,0,lev20,3,Cuiaba,-15.555244,-56.070214,234.000000
        Cuiaba,17:06:1993,12:00:00,168,-999.,0.092246,0.099877,-999.,-999.,0.110915,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,0.144628,-999.,-999.,-999.,0.187276,2.592902,-999.,-999.,-999.,-999.,-999.,-999.,-999.,0.547807,-999.,0.628609,-999.,0.988320,-999.,0,16,16,0,0,16,0,0,0,0,0,0,0,0,0,0,0,16,0,0,0,16,32,0,0,0,0,0,0,0,16,0,16,0,16,0,lev20,3,Cuiaba,-15.555244,-56.070214,234.000000
        """
        self._filename = filename
        self._stations = {}
        self._data = {}  # var -> {data-array}
        self._set_filters(filters)
        self._header = []

        self._revision = datetime.datetime.min
        self.fill_country_flag = fill_country_flag
        self.ts_type = ts_type

    def _read(
        self,
        tqdm_desc="reading stations",
    ):
        # check if file is a URL
        _laststatstr = ""
        # check if the data has been read already
        if len(self._data) != 0:
            return
        if self.is_valid_url(self._filename):
            # try to open as zipfile
            try:
                r = requests.get(self._filename)
                zip_ref = ZipFile(BytesIO(r.content))
                for file in zip_ref.namelist():
                    with zip_ref.open(file) as response:
                        lines = [line.decode("utf-8") for line in response.readlines()]
                    # read only 1st file here
                    break
            except BadZipFile:
                response = urlopen(self._filename)
                lines = [line.decode("utf-8") for line in response.readlines()]

        else:
            with open(self._filename, newline="") as csvfile:
                lines = csvfile.readlines()

        for _hidx in range(HEADER_LINE_NO - 1):
            self._header.append(lines.pop(0))
        # get fields from header line although csv can do that as well since we might want to adjust these names
        self._fields = lines.pop(0).strip().split(",")

        gcd = Geocoder_Reverse_NE()
        crd = csv.DictReader(lines, fieldnames=self._fields, delimiter=DELIMITER)
        bar = tqdm(desc=tqdm_desc, total=len(lines), disable=None)
        for _ridx, row in enumerate(crd):
            bar.update(1)
            if row[SITE_NAME] != _laststatstr:
                _laststatstr = row[SITE_NAME]
                # new station
                station = row[SITE_NAME]
                lon = float(row[LON_NAME])
                lat = float(row[LAT_NAME])
                alt = float(row["Site_Elevation(m)"])
                if self.fill_country_flag:
                    try:
                        country = gcd.lookup(lat, lon)["ISO_A2_EH"]
                    except Geocoder_Reverse_Exception:
                        country = "NN"
                else:
                    country = "NN"

                # units of Aeronet data are always 1
                units = "1"
                if not station in self._stations:
                    self._stations[station] = Station(
                        {
                            "station": station,
                            "longitude": lon,
                            "latitude": lat,
                            "altitude": alt,
                            "country": country,
                            "url": "",
                            "long_name": station,
                        }
                    )
                # every line contains all variables, sometimes filled with NaNs though
                if _ridx == 0:
                    for variable in DATA_VARS:
                        if variable in self._data:
                            da = self._data[variable]
                            if da.units != units:
                                raise Exception(
                                    f"unit change from '{da.units}' to 'units'"
                                )
                        else:
                            da = NpStructuredData(variable, units)
                            self._data[variable] = da

            day, month, year = row[DATE_NAME].split(":")
            datestring = "-".join([year, month, day])
            datestring = "T".join([datestring, row[TIME_NAME]])
            self._revision = max(
                [
                    self._revision,
                    datetime.datetime.strptime(datestring, "%Y-%m-%dT%H:%M:%S"),
                ]
            )
            time_dummy = np.datetime64(datestring)
            start = time_dummy - TS_TYPE_DIFFS[self.ts_type]
            end = time_dummy + TS_TYPE_DIFFS[self.ts_type]

            ts_dummy_data = {}
            for variable in DATA_VARS:
                try:
                    value = float(row[variable])
                    if value == NAN_VAL:
                        value = np.nan
                    # store value in ts_dummy_data, so we don't need to perform the nan check
                    # for each component of calculated values again
                    ts_dummy_data[variable] = value
                except KeyError:
                    # computed variable
                    if variable == AOD550_NAME:
                        value = self.compute_od_from_angstromexp(
                            0.55,
                            ts_dummy_data[AOD440_NAME],
                            0.44,
                            ts_dummy_data[ANG4487_NAME],
                        )
                self._data[variable].append(
                    value, station, lat, lon, alt, start, end, Flag.VALID, np.nan
                )
        bar.close()

    def metadata(self):
        self._read()
        return dict(revision=datetime.datetime.strftime(self._revision, "%y%m%d%H%M%S"))

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

    def compute_od_from_angstromexp(
        self, to_lambda: float, od_ref: float, lambda_ref: float, angstrom_coeff: float
    ) -> float:
        """Compute AOD at specified wavelength

        Uses Angstrom coefficient and reference AOD to compute the
        corresponding wavelength shifted AOD

        Parameters
        ----------
        to_lambda : :obj:`float` or :obj:`ndarray`
            wavelength for which AOD is calculated
        od_ref : :obj:`float` or :obj:`ndarray`
            reference AOD
        lambda_ref : :obj:`float` or :obj:`ndarray`
            wavelength corresponding to reference AOD
        angstrom_coeff : :obj:`float` or :obj:`ndarray`
            Angstrom coefficient

        Returns
        -------
        :obj:`float` or :obj:`ndarray`
            AOD(s) at shifted wavelength

        """
        return od_ref * (lambda_ref / to_lambda) ** angstrom_coeff

    def calc_angstroem_coeff(
        self, od1: float, od2: float, wl1: float, wl2: float
    ) -> float:
        """
        small helper method to calculate angstroem coefficient

        :param od1:
        :param od2:
        :param wl1:
        :param wl2:
        :return:
        """
        return -np.log(od1 / od2) / np.log(wl1 / wl2)

    def is_valid_url(self, url):
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False


class AeronetSunTimeseriesEngine(AutoFilterReaderEngine.AutoFilterEngine):
    def reader_class(self):
        return AeronetSunTimeseriesReader

    def open(self, filename, *args, **kwargs) -> AeronetSunTimeseriesReader:
        return self.reader_class()(filename, *args, **kwargs)

    def description(self):
        return "Simple reader of AeronetSun-files using the pyaro infrastructure"

    def url(self):
        return "https://github.com/metno/pyaro-readers"
