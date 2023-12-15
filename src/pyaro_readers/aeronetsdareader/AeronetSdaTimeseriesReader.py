import csv
from io import BytesIO
from urllib.parse import urlparse
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile

from geocoder_reverse_natural_earth import (
    Geocoder_Reverse_NE,
    Geocoder_Reverse_Exception,
)
import numpy as np
import requests
from pyaro.timeseries import (
    AutoFilterReaderEngine,
    Data,
    Flag,
    NpStructuredData,
    Station,
)
from tqdm import tqdm

# default URL
BASE_URL = "https://aeronet.gsfc.nasa.gov/data_push/V3/All_Sites_Times_Daily_Averages_SDA20.zip"
BASE_URL_TAR = "https://aeronet.gsfc.nasa.gov/data_push/V3/SDA/SDA_Level20_Daily_V3.tar.gz"
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
DATE_NAME = "Date_(dd:mm:yyyy)"
TIME_NAME: str = "Time_(hh:mm:ss)"
AOD500_NAME = "Total_AOD_500nm[tau_a]"
AOD500GT1_NAME = "Coarse_Mode_AOD_500nm[tau_c]"
AOD500LT1_NAME = "Fine_Mode_AOD_500nm[tau_f]"
ANG50_NAME = "Angstrom_Exponent(AE)-Total_500nm[alpha]"
ETA50LT1_NAME = "FineModeFraction_500nm[eta]"
AOD550GT1_NAME = "AODGT1_550nm"
AOD550LT1_NAME = "AODLT1_550nm"

DATA_VARS = [AOD500_NAME, AOD500GT1_NAME, AOD500LT1_NAME, ANG50_NAME, ETA50LT1_NAME]
COMPUTED_VARS = [AOD550GT1_NAME, AOD550LT1_NAME]
# The computed variables have to be named after the read ones, otherwise the calculation will fail!
DATA_VARS.extend(COMPUTED_VARS)

FILL_COUNTRY_FLAG = False


class AeronetSdaTimeseriesReader(AutoFilterReaderEngine.AutoFilterReader):
    def __init__(
        self,
        filename,
        filters=[],
        fill_country_flag: bool = FILL_COUNTRY_FLAG,
        tqdm_desc: [str, None] = None,
    ):
        """open a new csv timeseries-reader

                :param filename: str
                :param filters:
                :param fill_country_flag:
                :param tqdm_desc:
                :param filename_or_obj_or_url: path-like object to csv-file

                input file looks like this:
Version 3: SDA Retrieval Level 2.0
The following data are automatically cloud cleared and quality assured with pre-field and post-field calibration applied.
Contact: PI=Pawan Gupta and Elena Lind; PI Email=Pawan.Gupta@nasa.gov and Elena.Lind@nasa.gov
Daily Averages,UNITS can be found at,,, https://aeronet.gsfc.nasa.gov/new_web/units.html
AERONET_Site,Date_(dd:mm:yyyy),Time_(hh:mm:ss),Day_of_Year,Total_AOD_500nm[tau_a],Fine_Mode_AOD_500nm[tau_f],Coarse_Mode_AOD_500nm[tau_c],FineModeFraction_500nm[eta],2nd_Order_Reg_Fit_Error-Total_AOD_500nm[regression_dtau_a],RMSE_Fine_Mode_AOD_500nm[Dtau_f],RMSE_Coarse_Mode_AOD_500nm[Dtau_c],RMSE_FineModeFraction_500nm[Deta],Angstrom_Exponent(AE)-Total_500nm[alpha],dAE/dln(wavelength)-Total_500nm[alphap],AE-Fine_Mode_500nm[alpha_f],dAE/dln(wavelength)-Fine_Mode_500nm[alphap_f],N[Total_AOD_500nm[tau_a]],N[Fine_Mode_AOD_500nm[tau_f]],N[Coarse_Mode_AOD_500nm[tau_c]],N[FineModeFraction_500nm[eta]],N[2nd_Order_Reg_Fit_Error-Total_AOD_500nm[regression_dtau_a]],N[RMSE_Fine_Mode_AOD_500nm[Dtau_f]],N[RMSE_Coarse_Mode_AOD_500nm[Dtau_c]],N[RMSE_FineModeFraction_500nm[Deta]],N[Angstrom_Exponent(AE)-Total_500nm[alpha]],N[dAE/dln(wavelength)-Total_500nm[alphap]],N[AE-Fine_Mode_500nm[alpha_f]],N[dAE/dln(wavelength)-Fine_Mode_500nm[alphap_f]],Data_Quality_Level,AERONET_Instrument_Number,AERONET_Site_Name,Site_Latitude(Degrees),Site_Longitude(Degrees),Site_Elevation(m),
Cuiaba,16:06:1993,12:00:00,167,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,0,0,0,0,0,0,0,0,0,0,0,0,lev20,3,Cuiaba,-15.555244,-56.070214,234.000000
Cuiaba,17:06:1993,12:00:00,168,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,0,0,0,0,0,0,0,0,0,0,0,0,lev20,3,Cuiaba,-15.555244,-56.070214,234.000000
Cuiaba,19:06:1993,12:00:00,170,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,-999.,0,0,0,0,0,0,0,0,0,0,0,0,lev20,3,Cuiaba,-15.555244,-56.070214,234.000000

        """
        self._filename = filename
        self._stations = {}
        self._data = {}  # var -> {data-array}
        self._filters = filters
        self._header = []
        _laststatstr = ""

        # check if file is a URL
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
        bar = tqdm(desc=tqdm_desc, total=len(lines))
        for _ridx, row in enumerate(crd):
            bar.update(1)
            if row[SITE_NAME] != _laststatstr:
                _laststatstr = row[SITE_NAME]
                # new station
                station = row[SITE_NAME]
                lon = float(row[LON_NAME])
                lat = float(row[LAT_NAME])
                alt = float(row["Site_Elevation(m)"])
                if fill_country_flag:
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
            start = np.datetime64(datestring)
            end = start

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
                    if variable == AOD550GT1_NAME:
                        # ang_dummy = self.calc_angstroem_coeff(ts_dummy_data[AOD440_NAME], ts_dummy_data[AOD870_NAME], 0.44, 0.87)
                        value = self.compute_od_from_angstromexp(
                            0.55,
                            ts_dummy_data[AOD500GT1_NAME],
                            0.50,
                            ts_dummy_data[ANG50_NAME],
                        )
                self._data[variable].append(
                    value, station, lat, lon, alt, start, end, Flag.VALID, np.nan
                )
        bar.close()

    def _unfiltered_data(self, varname) -> Data:
        return self._data[varname]

    def _unfiltered_stations(self) -> dict[str, Station]:
        return self._stations

    def _unfiltered_variables(self) -> list[str]:
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


class AeronetSdaTimeseriesEngine(AutoFilterReaderEngine.AutoFilterEngine):
    def reader_class(self):
        return AeronetSdaTimeseriesReader

    def open(self, filename, *args, **kwargs) -> AeronetSdaTimeseriesReader:
        return self.reader_class()(filename, *args, **kwargs)

    def description(self):
        return "Simple reader of AeronetSDA-files using the pyaro infrastructure"

    def url(self):
        return "https://github.com/metno/pyaro-readers"
