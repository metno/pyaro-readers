import datetime
import glob
import inspect
import json
import logging
import os
import netCDF4
import numpy as np
from pyaro.timeseries import (
    AutoFilterReaderEngine,
    Data,
    NpStructuredData,
    Station,
)
import pyaro.timeseries.Filter
import xarray as xr
import datetime


logger = logging.getLogger(__name__)


class Netcdf_RWTimeseriesException(Exception):
    pass


class Netcdf_RWTimeseriesReader(AutoFilterReaderEngine.AutoFilterReader):
    """Initialize/open a new reader for netcdf-files

    :param filename: directory name for pyaro_netcdf_rw.YYYY.nc, e.g.
        /lustre/storeB/users/heikok/Ebas_converted/
    :param mode: 'r' for read-only, 'w' for writable
    :param filters: list of filters, defaults to []
        files are parsed a per year, so adding a pyaro.timeseries.Filter.TimeBoundsFilter
        is an advantage
    """

    def __init__(
        self,
        filename,
        mode="r",
        filters=[],
    ):
        self._set_filters(filters)
        self._mode = mode

        if os.path.isdir(filename):
            self._directory = filename
        else:
            if mode != "r":
                raise Netcdf_RWTimeseriesException(
                    f"no such file or directory: {filename}"
                )
            else:
                os.makedirs(filename)

        dataglob = os.path.join(self._directory, f"{self.ncfile_prefix}.????.nc")
        self._years = set()
        for file in glob.iglob(dataglob):
            year = file[-7:-3]
            if self._is_year_in_filters(year):
                self._years.add(year)

        try:
            self._variables = self._read_json("variables.json", [])
            self._metadata = self._read_json("metadata.json", {})
            self._stations = self._read_stations()
        except Exception as ex:
            raise Netcdf_RWTimeseriesException(f"unable to read definition-file: {ex}")

        self._metadata = self.metadata()

        return

    ncfile_prefix = "pyaro_netcdf_rw"

    def iterate_files(self):
        for y in self._years:
            file_path = os.path.join(self._directory, f"{self.ncfile_prefix}.{y}.nc")
            if os.path.exists(file_path):
                yield file_path

    def metadata(self):
        metadata = dict()
        date = datetime.datetime.min
        for f in self.iterate_files():
            with xr.open_dataset(f) as d:
                hist = d.attrs.get("last_changed", None)

                try:
                    datestr = hist.split("//")[0]
                    new_date = datetime.datetime.strptime(
                        datestr, "%a %b %d %H:%M:%S %Y"
                    )
                except Exception:
                    try:
                        hist = d.attrs.get("history", "")[-1]
                        datestr = " ".join(hist.split(" ")[:2])
                        new_date = datetime.datetime.strptime(
                            datestr, "%Y-%m-%d %H:%M:%S"
                        )
                    except Exception:
                        new_date = datetime.datetime.min

                if new_date > date:
                    date = new_date

        metadata["revision"] = datetime.datetime.strftime(date, "%y%m%d%H%M%S")

        return metadata

    def _read_json(self, file, empty):
        filepath = os.path.join(self._directory, file)
        res = empty
        if os.path.exists(filepath):
            with open(filepath, "r") as fh:
                res = json.load(fh)
        return res

    def _write_json(self, obj, file):
        filepath = os.path.join(self._directory, file)
        with open(filepath, "w") as fh:
            json.dump(obj, fh)
        return

    def _read_stations(self) -> dict[str, Station]:
        stat_dict = {}
        for stat, stat_kwargs in self._read_json("stations.json", {}).items():
            stat_dict[stat] = Station(**stat_kwargs)
        return stat_dict

    def _write_stations(self):
        stat_obj = {}
        for stat, station in self.stations().items():
            if pyaro.__version__ > "0.0.10":
                stat_obj[stat] = station.init_kwargs()
            else:
                stat_obj[stat] = {
                    "fields": station._fields,
                    "metadata": station.metadata,
                }
        self._write_json(stat_obj, "stations.json")

    def _is_year_in_filters(self, year):
        start_year = np.datetime64(f"{year}-01-01 00:00:00")
        end_year = np.datetime64(f"{year}-12-31 23:59:59")
        time_filter = pyaro.timeseries.Filter.TimeBoundsFilter()
        for fil in self._get_filters():
            if isinstance(fil, pyaro.timeseries.Filter.TimeBoundsFilter):
                time_filter = fil
        if time_filter.has_envelope():
            start, end = time_filter.envelope()
            if end_year < start:
                return False
            if end < start_year:
                return False
        return True

    def _get_data_from_ncfile(
        self, varname, file, data: NpStructuredData
    ) -> NpStructuredData:
        with netCDF4.Dataset(file, "r") as nc:
            pos = nc.variable_names.index(varname)
            if pos < 0:
                logger.info(f"{varname} not in file {file}")
                return data
            if f"start_times_{pos}" not in nc.variables:
                logger.info(f"{varname} not in file {file}, pos {pos}")
                return data

            start_times = netCDF4.num2date(
                nc[f"start_times_{pos}"][:], nc[f"start_times_{pos}"].units
            )
            end_times = netCDF4.num2date(
                nc[f"end_times_{pos}"][:], nc[f"end_times_{pos}"].units
            )
            data_name = f"values_{pos}"
            data_is_new = len(data) == 0 and data.units == ""
            if data_is_new:
                data = NpStructuredData(varname, nc[data_name].units)
            if data.units != "" and nc[data_name].units != data.units:
                logger.warning(
                    f"units-change for {varname}/{data_name} in {file}: {nc[data_name].units} != {data.units}"
                )

            data.append(
                nc[data_name][:].filled(np.nan),
                nc[f"stations_{pos}"][:].astype("U64"),
                nc[f"latitudes_{pos}"][:].filled(np.nan),
                nc[f"longitudes_{pos}"][:].filled(np.nan),
                nc[f"altitudes_{pos}"][:].filled(np.nan),
                start_times,
                end_times,
                nc[f"flags_{pos}"][:].filled(-32767),
                nc[f"standard_deviations_{pos}"][:].filled(np.nan),
            )
        return data

    def _tmp_and_real_ncfilename(self, year):
        tmpfile = os.path.join(
            self._directory, f"{self.ncfile_prefix}.{year}.nc.{os.getpid()}"
        )
        file = os.path.join(self._directory, f"{self.ncfile_prefix}.{year}.nc")
        return (tmpfile, file)

    def _tmp_ncfile(self, year, readerstr):
        tmpfile, file = self._tmp_and_real_ncfilename(year)
        tmpnc = netCDF4.Dataset(tmpfile, "w", format="NETCDF4")
        if os.path.exists(file):
            with netCDF4.Dataset(file, "r") as nc:
                vars = nc.variable_names
                for var in self.variables():
                    if not var in vars:
                        vars.append(var)
                tmpnc.variable_names = vars
                oldhistory = nc.history
                if isinstance(oldhistory, str):
                    oldhistory = [oldhistory]
                tmpnc.history = oldhistory + [
                    f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} updated with netcdf_rw from {readerstr}"
                ]

        else:
            tmpnc.variable_names = self.variables()
            tmpnc.history = [
                f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} creation with netcdf_rw from {readerstr}"
            ]
        return tmpnc

    def _update_ncfile(self, nc, year, data):
        """write the data to a nc-file, creating if needed

        :param nc: writeable nc-file, with variable_names global attribute
        :param year: year of data
        :param data: filtered data for one year
        """
        var_name = data.variable
        units = data.units
        pos = nc.variable_names.index(var_name)
        if pos < 0:
            raise Netcdf_RWTimeseriesException(
                f"{var_name} not in {nc.variable_names} for {year}"
            )
        dim_name = f"dim_{pos}"
        nc.createDimension(dim_name, len(data))
        for x in data.keys():
            if "time" in x:
                var = nc.createVariable(
                    f"{x}_{pos}", np.int64, (dim_name), compression="zlib"
                )
                var.units = "seconds since 1970-01-01 00:00:00 +00:00"
                var[:] = data[x].astype("datetime64[s]").astype("int64")
            else:
                compression = "zlib"
                if x == "stations":
                    compression = False
                var = nc.createVariable(
                    f"{x}_{pos}", data[x].dtype, (dim_name), compression=compression
                )
                if x == "altitudes":
                    var.units = "m"
                    var.standard_name = "altitude"
                    var.positive = "up"
                if x == "longitudes":
                    var.units = "degrees_east"
                if x == "latitudes":
                    var.units = "degrees_north"
                if x == "values":
                    var.units = units
                    var.long_name = var_name
                    var.coordinates = (
                        f"longitudes_{pos} latitudes_{pos} altitudes_{pos}"
                    )
                var[:] = data[x]

    def add(self, reader: pyaro.timeseries.Reader):
        """add content of another reader to this netcdf_rw database

        All content will be added, except for duplicates which will be removed.

        :param reader: another pyaro-Reader including filters
        """
        if self._mode == "r":
            raise Netcdf_RWTimeseriesException(
                f"add() not allowed on readonly (mode='{self._mode}') data-dir"
            )
        self._metadata = reader.metadata() | self._metadata
        self._stations = reader.stations() | self._stations
        org_variables = self._variables
        self._variables = list(set(org_variables + reader.variables()))

        ncfiles = {}
        for var in reader.variables():
            logger.info(f"adding variable {var}")
            if var in org_variables:
                data = self.data(var)
                if var in reader.variables():
                    rdata = reader.data(var)
                    if data.units != rdata.units:
                        raise Netcdf_RWTimeseriesException(
                            f"change of unit for variable {var} from {data.units} to {rdata.units}"
                        )
                    data.append(
                        rdata.values,
                        rdata.stations,
                        rdata.latitudes,
                        rdata.longitudes,
                        rdata.altitudes,
                        rdata.start_times,
                        rdata.end_times,
                        rdata.flags,
                        rdata.standard_deviations,
                    )
            else:
                data = reader.data(var)
            data = pyaro.timeseries.Filter.DuplicateFilter().filter_data(
                data, self.stations(), self.variables()
            )
            min_year = (
                np.min(data.start_times).astype("datetime64[Y]").astype(int) + 1970
            )
            max_year = np.max(data.end_times).astype("datetime64[Y]").astype(int) + 1970
            for year in range(min_year, max_year + 1):
                if not year in ncfiles:
                    ncfiles[year] = self._tmp_ncfile(year, str(reader))
                ydata = pyaro.timeseries.Filter.TimeBoundsFilter(
                    startend_include=[
                        (f"{year}-01-01 00:00:00", f"{year}-12-31 23:59:59")
                    ]
                ).filter_data(data, self.stations(), self.variables())
                self._update_ncfile(ncfiles[year], year, ydata)

        # make the new files available
        for year in ncfiles:
            ncfiles[year].close()
            tmpfile, file = self._tmp_and_real_ncfilename(year)
            os.rename(tmpfile, file)
        self._write_stations()
        self._write_json(self.metadata(), "metadata.json")
        self._write_json(self._variables, "variables.json")
        return

    def _unfiltered_data(self, varname) -> Data:
        data = NpStructuredData(varname, "")
        for year in self._years:
            file = os.path.join(self._directory, f"{self.ncfile_prefix}.{year}.nc")
            if not os.path.exists(file):
                logger.info(f"no datafile for {year} like {file}, skipping...")
                continue
            data = self._get_data_from_ncfile(varname, file, data)

        return data

    def _unfiltered_stations(self) -> dict[str, Station]:
        return self._stations

    def _unfiltered_variables(self) -> list[str]:
        return self._variables

    def close(self):
        pass


class Netcdf_RWTimeseriesEngine(AutoFilterReaderEngine.AutoFilterEngine):
    """Ascii-files converted by MSC-W to netcdf-format, e.g. using niluAscii2netcdf or eea_airquip2emepdata.py"""

    def reader_class(self):
        return Netcdf_RWTimeseriesReader

    def open(self, filename, *args, **kwargs) -> Netcdf_RWTimeseriesReader:
        return self.reader_class()(filename, *args, **kwargs)

    def description(self) -> str:
        return inspect.doc(self)

    def url(self):
        return "https://github.com/metno/pyaro-readers"

    def read(self):
        return self.reader_class().read()
