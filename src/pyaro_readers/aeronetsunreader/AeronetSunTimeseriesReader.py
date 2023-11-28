import csv
import numpy as np
from pyaro.timeseries import Data, NpStructuredData, Flag, Reader, Station, Engine


class AeronetSunTimeseriesReader(Reader):
    def __init__(
        self,
        filename,
        columns=dict(
            variable=0,
            station=1,
            longitude=2,
            latitude=3,
            value=4,
            units=5,
            start_time=6,
            end_time=7,
        ),
        variable_units={"SOx": "Gg", "NOx": "Mg"},
        csvreader_kwargs={"delimiter": ","},
        filters=[],
    ):
        """open a new csv timeseries-reader

        :param filename_or_obj_or_url: path-like object to csv-file
        """
        self._filename = filename
        self._stations = {}
        self._data = {}  # var -> {data-array}
        self._filters = filters
        with open(self._filename, newline="") as csvfile:
            crd = csv.reader(csvfile, **csvreader_kwargs)
            for row in crd:
                variable = row[columns["variable"]]
                value = float(row[columns["value"]])
                station = row[columns["station"]]
                lon = float(row[columns["longitude"]])
                lat = float(row[columns["latitude"]])
                start = np.datetime64(row[columns["start_time"]])
                end = np.datetime64(row[columns["end_time"]])
                if "altitude" in columns:
                    alt = float(row[columns["altitude"]])
                else:
                    alt = 0
                if "units" in columns:
                    units = row[columns["units"]]
                else:
                    units = variable_units[variable]

                if variable in self._data:
                    da = self._data[variable]
                    if da.units != units:
                        raise Exception(f"unit change from '{da.units}' to 'units'")
                else:
                    da = NpStructuredData(variable, units)
                    self._data[variable] = da
                da.append(value, station, lat, lon, alt, start, end, Flag.VALID, np.nan)
                if not station in self._stations:
                    self._stations[station] = Station(
                        {
                            "station": station,
                            "longitude": lon,
                            "latitude": lat,
                            "altitude": 0,
                            "country": "NO",
                            "url": "",
                            "long_name": station,
                        }
                    )

    def _unfiltered_data(self, varname) -> Data:
        return self._data[varname]

    def _unfiltered_stations(self) -> dict[str, Station]:
        return self._stations

    def _unfiltered_variables(self) -> list[str]:
        return list(self._data.keys())

    def variables(self) -> list[str]:
        vars = self._unfiltered_variables()
        for fi in self._filters:
            vars = fi.filter_variables(vars)
        return vars

    def stations(self) -> dict[str, Station]:
        stats = self._unfiltered_stations()
        for fi in self._filters:
            stats = fi.filter_stations(stats)
        return stats

    def data(self, varname) -> Data:
        dat = self._unfiltered_data(varname)
        stats = self._unfiltered_stations()
        vars = self._unfiltered_variables()
        for fi in self._filters:
            dat = fi.filter_data(dat, stats, vars)
        return dat

    def close(self):
        pass


class AeronetSunTimeseriesEngine(Engine):
    def open(self, filename, *args, **kwargs) -> AeronetSunTimeseriesReader:
        return AeronetSunTimeseriesReader(filename, *args, **kwargs)

    def args(self):
        return (
            "filename",
            "columns",
            "aeronetsunreader_kwargs",
            "variable_units",
            "filters",
        )

    def supported_filters(self):
        return ""

    def description(self):
        return "Simple reader of AeronetSun-files using python AeronetSun-reader"

    def url(self):
        return "https://github.com/metno/pyaro"
