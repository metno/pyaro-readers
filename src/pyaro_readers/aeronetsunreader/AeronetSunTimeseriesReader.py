import csv
import numpy as np
from pyaro.timeseries import Data, NpStructuredData, Flag, AutoFilterReaderEngine, Station, Engine
import requests, zipfile, io
import geocoder
from tqdm import tqdm

# default URL
BASE_URL = "https://aeronet.gsfc.nasa.gov/data_push/V3/All_Sites_Times_Daily_Averages_AOD20.zip"
# number of lines to read before the reading is handed to Pythobn's csv reader
HEADER_LINE_NO = 7
DELIMITER = ","
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

DATA_VARS = [AOD500_NAME, ANG4487_NAME, AOD440_NAME, AOD870_NAME]
FILL_COUNTRY_FLAG = False

# further vars can be added here
VARS_TO_STORE = [
    LAT_NAME,
    LON_NAME,
    ALT_NAME,
    SITE_NAME,
    DATE_NAME,
    TIME_NAME,
    AOD500_NAME,
    ANG4487_NAME,
    AOD440_NAME,
    AOD870_NAME,
    "AERONET_Instrument_Number",
    "Data_Quality_Level",
]


class AeronetSunTimeseriesReader(
    AutoFilterReaderEngine.AutoFilterReader
):
    def __init__(
        self,
        filename,
        csvreader_kwargs={"delimiter": DELIMITER},
        filters=[],
    ):
        """open a new csv timeseries-reader

                :param filename_or_obj_or_url: path-like object to csv-file

                input file looks like this:
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
        self._filters = filters
        self._header = []
        _laststatstr = ""
        with open(self._filename, newline="") as csvfile:
            for _hidx in range(HEADER_LINE_NO - 1):
                self._header.append(csvfile.readline())
            # get fields from header line although csv can do that as well since we might want to adjust these names
            self._fields = csvfile.readline().strip().split(",")

            crd = csv.DictReader(csvfile, fieldnames=self._fields, **csvreader_kwargs)
            for _ridx, row in enumerate(crd):
                if row[SITE_NAME] != _laststatstr:
                    print(f"reading station {row[SITE_NAME]}...")
                    _laststatstr = row[SITE_NAME]
                    # new station
                    station = row[SITE_NAME]
                    lon = float(row[LON_NAME])
                    lat = float(row[LAT_NAME])
                    alt = float(row["Site_Elevation(m)"])
                    if FILL_COUNTRY_FLAG:
                        try:
                            country = geocoder.osm([lat, lon], method="reverse").json[
                                "country_code"
                            ]
                        except:
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
                for variable in DATA_VARS:
                    day, month, year = row[DATE_NAME].split(":")
                    datestring = "-".join([year, month, day])
                    datestring = "T".join([datestring, row[TIME_NAME]])
                    start = np.datetime64(datestring)
                    end = start
                    value = float(row[variable])
                    self._data[variable].append(
                        value, station, lat, lon, alt, start, end, Flag.VALID, np.nan
                    )

    def _unfiltered_data(self, varname) -> Data:
        return self._data[varname]

    def _unfiltered_stations(self) -> dict[str, Station]:
        return self._stations

    def _unfiltered_variables(self) -> list[str]:
        return list(self._data.keys())

    def close(self):
        pass


class AeronetSunTimeseriesEngine(Engine):
    def open(self, filename, *args, **kwargs) -> AeronetSunTimeseriesReader:
        return AeronetSunTimeseriesReader(filename, *args, **kwargs)

    def args(self):
        return (
            "filename",
            "columns",
            "reader_kwargs",
            "variable_units",
            "filters",
        )

    def supported_filters(self):
        return ""

    def description(self):
        return "Simple reader of AeronetSun-files using the pyaro infrastructure"

    def url(self):
        return "https://github.com/metno/pyaro-readers"
