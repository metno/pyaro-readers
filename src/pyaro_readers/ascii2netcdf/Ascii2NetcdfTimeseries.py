import csv
import glob
import inspect
import logging
import os
import netCDF4
import numpy as np
from pyaro.timeseries import (
    AutoFilterReaderEngine,
    Data,
    Flag,
    NpStructuredData,
    Station
)
import pyaro.timeseries.Filter

logger = logging.getLogger(__name__)

class Ascii2NetcdfTimeseriesReaderException(Exception):
    pass

class Ascii2NetcdfTimeseriesReader(AutoFilterReaderEngine.AutoFilterReader):
    RESOLUTIONS = {60*60: 'hourly',
                   60*60*24: 'daily',
                   60*60*24*7: 'weekly',
                   60*60*24*28: 'monthly',
                   60*60*24*365: 'yearly'}
    def __init__(
        self,
        filename,
        filters=[],
    ):
        """Initialize/open a new reader for netcdf-files converted from EBAS NASA-Ames-files
        with niluNasaAmes2netcdf.pl.

        :param filename: directory name for data_daily.YYYY.nc, e.g.
            /lustre/storeB/project/fou/kl/emep/Auxiliary/NILU
        :param filters: list of filters, defaults to []
        """
        self._set_filters(filters)
        if os.path.is_directory(filename):
            self._directory = filename
        else:
            raise Ascii2NetcdfTimeseriesReaderException(f"no such file or directory: {filename}")

        dataglob = os.path.join(self._directory, "data_*.????.nc")
        self._years = set()
        for file in glob.iglob(dataglob):
            year = file[-7:-3]
            if self._is_year_in_filters(year):
                self._years.add(year)

        self._resolutions = self.RESOLUTIONS.values() # TODO, pre-filter resolutions

        self._variables = self._read_file_variables()
        station_file = 'StationList.csv'
        station_filepath = os.path.join(self._directory, station_file)
        if os.exists(station_filepath):
            self._stations = self._read_station_list(station_filepath)
        else:
            dirname = os.path.basename(self._directory)
            station_file = dirname + station_file # e.g. AirbaseStationList.csv
            station_filepath = os.path.join(self._directory, station_file)
            if os.exists(station_filepath):
                self._stations = self._read_station_list(station_filepath)
            else:
                raise Ascii2NetcdfTimeseriesReaderException(
                    f"no stations: StationList.csv or {station_file} not found in {self._directory}"
                )
        return

    def _is_year_in_filters(self, year):
        start_year = np.datetime64(f"{year}-01-01 00:00:00")
        end_year = np.datetime64(f"{year}-12-31 23:59:59")
        time_filter = pyaro.timeseries.Filter.TimeBoundsFilter()
        for fil in self._get_filters():
            if isinstance(fil, pyaro.timeseries.Filter.TimeBoundsFilter):
                time_filter = fil
        if fil.has_envelope():
            start, end = time_filter.envelope()
            if end_year < start:
                return False
            if end < start_year:
                return False
        return True

    def _read_file_variables(self):
        variables = {}
        for resolution in self.RESOLUTIONS.values():
            for year in self._years:
                file = os.path.join(self._directory, f"data_{resolution}.{year}.nc")
                if not os.path.exists(file):
                    logger.info(f"no datafile for {year} and {resolution} at {file}, skipping...")
                    continue
                with netCDF4.Dataset(file, 'r') as nc:
                    for vname, var in nc.variables.items():
                        if vname.startswith('EPDL'):
                            varname = f"{var.component}_in_{var.matrix}"
                            units = "1"
                            if 'units' in var.ncattrs():
                                units = var.units
                            if varname in variables:
                                if units != variables[varname][1]:
                                    raise Ascii2NetcdfTimeseriesReaderException(
                                        f"units changed from {variables[varname][1]} to {units} for {varname}/{vname} in {file}"
                                    )
                            variables[varname] = (vname, units)
        return variables

    def _read_station_list(self, file):
        stations = {}
        '#StationName	urban/suburban/rural	CountryName	ISO2	Latitude (degrees)	Longitude (degrees)	Altitude (m.a.s.l.)	LocationCode'
        with open(file, encoding="UTF-8", newline="") as fh:
            with csv.reader(fh, delimiter="\t") as csvfile:
                for row in csvfile:
                    if not len(row):
                        continue
                    if row[0].startswith("#"):
                        continue
                    if len(row) < 7:
                        logger.warning(r"missing elements in file {file}: {row}")
                        continue
                    if row[6] in stations:
                        logger.warning(r"duplicated station in file {file}: {row[6]}")
                    else:
                        stations[row[6]] = Station(
                            {
                                "station": row[6],
                                "longitude": float(row[4]),
                                "latitude": float(row[3]),
                                "altitude": float(row[5]),
                                "country": row[2],
                                "url": "",
                                "long_name": row[0],
                                # not used: rural/urban
                            }
                        )
        return stations

    def _get_data_from_ncfile(self, varname, file, data):
        with netCDF4.Dataset(file, 'r') as nc:
            start_times = netCDF4.num2date(nc['time'][:], nc['time'].units)
            end_times = start_times + (start_times[1]-start_times[0])
            stations = nc['station'][:]
            (epdl, _) = self._variables[varname]
            if not epdl in nc:
                return
            vdata = np.ma.filled(nc[epdl][:], np.nan)
            if nc[epdl].units != data.units:
                logger.warning(f"units-change for {varname} in {file}: {nc[epdl].units} != {data.units}")

            # get all arrays into same size, time fastes moving, i.e. [station][time]
            dstruct = {}
            dstruct['start_times'] = np.tile(start_times, vdata.shape[0])
            dstruct['end_times'] = np.tile(end_times, vdata.shape[0])
            lats = []
            lons = []
            alts = []
            for i in range(stations.shape[0]):
                station = str(netCDF4.chartostring(stations[i]))
                if not station in self.stations():
                    lats.append(np.nan)
                    lons.append(np.nan)
                    alts.append(np.nan)
                else:
                    stat = self._stations[station]
                    lats.append(stat.latitude)
                    lons.append(stat.longitude)
                    alts.append(stat.altitude)
            lat = np.array(lats)
            lon = np.array(lons)
            alt = np.array(alts)
            dstruct['stations'] = np.repeat(stations, vdata.shape[1])
            dstruct['lats'] = np.repeat(lat, vdata.shape[1])
            dstruct['lons'] = np.repeat(lon, vdata.shape[1])
            dstruct['alts'] = np.repeat(alt, vdata.shape[1])
            dstruct['data'] = vdata.flatten()

            # filter out undefined data or stations
            idx = np.isfinite(dstruct['data']) & np.isfinite(dstruct['lats'])
            for key in dstruct.keys():
                dstruct[key] = dstruct[key][idx]

            dstruct['flags'] = dstruct['data'].astype('i4')
            dstruct['flags'][:] = Flag.VALID

            data.append(dstruct['data'], dstruct['station'], dstruct['lats'],
                        dstruct['lons'], dstruct['alts'], dstruct['start'], dstruct['end'],
                        dstruct['flags'], dstruct['data']*np.nan)
            return


    def _unfiltered_data(self, varname) -> Data:
        (_, units) = self._variables[varname]
        data = Data.NpStructuredData(varname, units)

        for year in self._years:
            for resolution in self._resolutions:
                file = os.path.join(self._directory, f"data_{resolution}.{year}.nc")
                if not os.path.exists(file):
                    logger.info(f"no datafile for {year} and {resolution} at {file}, skipping...")
                    continue
                self._get_data_from_ncfile(varname, file, data)

        return self._data[varname]

    def _unfiltered_stations(self) -> dict[str, Station]:
        return self._stations

    def _unfiltered_variables(self) -> list[str]:
        return list(self._variables.keys())

    def close(self):
        pass


class Ascii2NetcdfTimeseriesReaderEngine(AutoFilterReaderEngine.AutoFilterEngine):
    """Ascii-files converted by MSC-W to netcdf-format, e.g. using niluAscii2netcdf or eea_airquip2emepdata.py"""

    def reader_class(self):
        return Ascii2NetcdfTimeseriesReader

    def open(self, filename, *args, **kwargs) -> Ascii2NetcdfTimeseriesReader:
        return self.reader_class()(filename, *args, **kwargs)

    def description(self) -> str:
        return inspect.doc(self)

    def url(self):
        return "https://github.com/metno/pyaro-readers"
