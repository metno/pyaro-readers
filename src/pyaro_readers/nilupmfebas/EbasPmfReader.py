import logging
import numpy as np
from .ebas_nasa_ames import EbasNasaAmesFile
from pyaro.timeseries import (
    AutoFilterReaderEngine,
    Data,
    Flag,
    NpStructuredData,
    Station,
)
from tqdm import tqdm
from pyaro_readers.units_helpers import UALIASES

from pathlib import Path
import re
import datetime


logger = logging.getLogger(__name__)

FILL_COUNTRY_FLAG = False
FILE_MASK = "*.nas"
FIELDS_TO_SKIP = ["start_time of measurement", "end_time of measurement"]


class EBASPMFReaderException(Exception):
    pass


class EbasPmfTimeseriesReader(AutoFilterReaderEngine.AutoFilterReader):
    def __init__(
        self,
        filename: Path | str,
        filters=[],
        tqdm_desc: str | None = None,
        filemask: str = FILE_MASK,
        vars_to_read: list[str] = None,
    ):
        self._filters = filters
        self._stations = {}
        self._data = {}  # var -> {data-array}
        self._set_filters(filters)
        self._header = []
        self._opts = {"default": ReadEbasOptions()}
        self._variables = {}
        self._metadata = {}
        self._revision = datetime.datetime.min
        self._filename = filename
        self._filemask = filemask
        self._vars_to_read = vars_to_read
        self._tqdm_desc = tqdm_desc

        # variable include filter comes like this
        # {'variables': {'include': ['PM10_density']}}
        # test for variable filter
        if "variables" in filters:
            if "include" in filters["variables"]:
                vars_to_read = filters["variables"]["include"]
                self._vars_to_read = vars_to_read
                logger.info(f"applying variable include filter {vars_to_read}...")

        self._realpath = Path(filename).resolve()

    def read(self):
        """read method"""

        # check if the data has been read already
        if len(self._data) != 0:
            return
        if Path(self._realpath).is_dir():
            # search directory for files
            files = list(self._realpath.glob(self._filemask))
            bar = tqdm(desc=self._tqdm_desc, total=len(files), disable=None)

            for _ridx, file in enumerate(files):
                bar.update(1)
                logger.info(file)
                self.read_file(file, vars_to_read=self._vars_to_read)
                if _ridx > 30:
                    assert True

            bar.close()
        elif Path(self._realpath).is_file():
            self.read_file(self._realpath)
        else:
            # filename is something else
            raise EBASPMFReaderException(f"No such file or directory: {self._filename}")

    def metadata(self):
        metadata = dict()
        metadata["revision"] = datetime.datetime.strftime(
            self._revision, "%y%m%d%H%M%S"
        )
        return metadata

    def read_file_basic(
        self,
        filename: Path | str,
    ):
        """Read EBAS NASA Ames file

        Parameters
        ----------
        filename : str
            absolute path to filename to read

        Returns
        -------
        EbasNasaAmesFile
            dict-like object containing results
        """
        data_out = EbasNasaAmesFile(filename)

        return data_out

    def read_file(self, filename: Path | str, vars_to_read: list[str] = None):
        """Read EBAS NASA Ames file and put the data in the object"""

        _file_dummy = self.read_file_basic(filename)
        self._revision = max(
            [
                self._revision,
                datetime.datetime.strptime(
                    _file_dummy.meta["revision_date"], "%Y%m%d%H%M%S"
                ),
            ]
        )

        matrix = _file_dummy.meta["matrix"]
        vars_read_in_file = []

        # multicolumn file: ebas var names come from _file_dummy.col_names_vars
        for var_idx, var_def in enumerate(_file_dummy.var_defs):
            # continue if the variable is not an actual data variable (but e.g. time)
            if not var_def.is_var:
                continue
            # skip additional fields...
            if var_def.name in FIELDS_TO_SKIP:
                continue
            # continue if the statistcs is to be ignored
            try:
                if var_def.statistics in self._opts["default"].ignore_statistics:
                    continue
            except KeyError:
                # sometimes there's no statistics: pass
                pass

            # adjust unit string
            unit = var_def.unit
            if unit in UALIASES:
                unit = UALIASES[unit]
            var_name = f"{matrix}#{_file_dummy.var_defs[var_idx].name}#{unit}"
            if vars_to_read is not None:
                if var_name not in vars_to_read:
                    continue
            if var_name not in self._variables:
                self._variables[var_name] = (
                    var_name,
                    unit,
                )

            var_unit = unit
            stat_name = _file_dummy.meta["station_code"]
            if stat_name not in self._stations:
                country = _file_dummy.meta["station_code"][0:2]
                # the location naming is not consistent
                # try the two we have seen so far
                try:
                    lat, lon, alt = self._get_station_loc_data(filename, _file_dummy)
                except EBASPMFReaderException:
                    return
                # prepare some station based metadata
                _meta_dummy = {}
                _meta_dummy["file_metadata"] = {
                    filename: {
                        "meta": _file_dummy.meta,
                        "var_defs": _file_dummy.var_defs,
                    }
                }

                self._stations[stat_name] = Station(
                    {
                        "station": stat_name,
                        "longitude": lon,
                        "latitude": lat,
                        "altitude": alt,
                        "country": country,
                        "url": "",
                        "long_name": stat_name,
                    },
                    metadata=_meta_dummy,
                )
            else:
                lat = self._stations[stat_name].latitude
                lon = self._stations[stat_name].longitude
                alt = self._stations[stat_name].altitude

            # put only the 1st match in the data...
            # because that is the one we should be interested in
            if var_name in vars_read_in_file:
                logger.info(
                    f"Warning! Variable {var_name} is already used in current file! Only important if the data looks wrong. Skipping..."
                )
                continue
            else:
                vars_read_in_file.append(var_name)

            if var_name not in self._data:
                # we might want to put a CF compliant unit here
                self._data[var_name] = NpStructuredData(var_name, var_unit)

            # now add ts after ts
            for t_idx, ts in enumerate(_file_dummy.start_meas):
                self._data[var_name].append(
                    float(_file_dummy.data[t_idx, var_idx]),  # value
                    stat_name,
                    lat,
                    lon,
                    alt,
                    ts,
                    _file_dummy.stop_meas[t_idx],
                    Flag.VALID,
                    np.nan,
                )

    def _unfiltered_data(self, varname) -> Data:
        self.read()
        return self._data[varname]

    def _unfiltered_stations(self) -> dict[str, Station]:
        self.read()
        return self._stations

    def _unfiltered_variables(self) -> list[str]:
        self.read()
        return list(self._data.keys())

    def close(self):
        pass

    def _get_station_loc_data(
        self, filename: str, _file_dummy: EbasNasaAmesFile
    ) -> tuple[float, float, float]:
        try:
            lat = float(_file_dummy.meta["station_latitude"])
            lon = float(_file_dummy.meta["station_longitude"])
            alt_str = _file_dummy.meta["station_altitude"]
        except KeyError:
            # might not always work either
            try:
                lat = float(_file_dummy.meta["measurement_latitude"])
                lon = float(_file_dummy.meta["measurement_longitude"])
                alt_str = _file_dummy.meta["measurement_altitude"]
            except KeyError:
                logger.info(
                    f"no lat / lon found in file {filename}. Skipping the file..."
                )
                raise EBASPMFReaderException
        try:
            # usually there's a blank between the value and the unit
            alt = float(alt_str.split(" ")[0])
        except ValueError:
            # but unfortunately not always
            # remove all non numbers
            alt = float(re.sub(r"[^\d.-]+", "", alt_str))
        return lat, lon, alt


class EbasPmfTimeseriesEngine(AutoFilterReaderEngine.AutoFilterEngine):
    def reader_class(self):
        return EbasPmfTimeseriesReader

    def open(self, filename, *args, **kwargs) -> EbasPmfTimeseriesReader:
        return self.reader_class()(filename, *args, **kwargs)

    def description(self):
        return "Simple reader of EBAS NASA-Ames files using the pyaro infrastructure"

    def url(self):
        return "https://github.com/metno/pyaro-readers"


class ReadEbasOptions(dict):
    """Options for EBAS reading routine

    Attributes
    ----------
    prefer_statistics : list
        preferred order of data statistics. Some files may contain multiple
        columns for one variable, where each column corresponds to one of the
        here defined statistics that where applied to the data. This attribute
        is only considered for ebas variables, that have not explicitely defined
        what statistics to use (and in which preferred order, if applicable).
        Reading preferences for all Ebas variables are specified in the file
        ebas_config.ini in the data directory of pyaerocom.
    ignore_statistics : list
        columns that have either of these statistics applied are ignored for
        variable data reading.
    wavelength_tol_nm : int
        Wavelength tolerance in nm for reading of (wavelength dependent)
        variables. If multiple matches occur (e.g. query -> variable at 550nm
        but file contains 3 columns of that variable, e.g. at 520, 530 and
        540 nm), then the closest wavelength to the queried wavelength is used
        within the specified tolerance level.
    shift_wavelengths : bool
        (only for wavelength dependent variables).
        If True, and a data columns candidate is valid within wavelength
        tolerance around desired wavelength, that column will be considered
        to be used for data import. Defaults to True.
    assume_default_ae_if_unavail : bool
        assume an Angstrom Exponent for applying wavelength shifts of data. See
        :attr:`ReadEbas.ASSUME_AE_SHIFT_WVL` and
        :attr:`ReadEbas.ASSUME_AAE_SHIFT_WVL` for AE and AAE assumptions
        related to scattering and absorption coeffs. Defaults to True.
    check_correct_MAAP_wrong_wvl : bool
        (BETA, do not use): set correct wavelength for certain absorption coeff
        measurements. Defaults to False.
    eval_flags : bool
        If True, the flag columns in the NASA Ames files are read and decoded
        (using :func:`EbasFlagCol.decode`) and the (up to 3 flags for each
        measurement) are evaluated as valid / invalid using the information
        in the flags CSV file. The evaluated flags are stored in the
        data files returned by the reading methods :func:`ReadEbas.read`
        and :func:`ReadEbas.read_file`.
    keep_aux_vars : bool
        if True, auxiliary variables required for computed variables will be
        written to the :class:`UngriddedData` object created in
        :func:`ReadEbas.read` (e.g. if sc550dryaer is requested, this
        requires reading of sc550aer and scrh. The latter 2 will be
        written to the data object if this parameter evaluates to True)
    convert_units : bool
        if True, variable units in EBAS files will be checked and attempted to
        be converted into AeroCom default unit for that variable. Defaults to
        True.
    try_convert_vmr_conc : bool
        attempt to convert vmr data to conc if user requires conc (e.g. user
        wants conco3 but file only contains vmro3), and vice versa.
    ensure_correct_freq : bool
        if True, the frequency set in NASA Ames files (provided via attr
        *resolution_code*) is checked using time differences inferred from
        start and stop time of each measurement. Measurements that are not in
        that resolution (within 5% tolerance level) will be flagged invalid.
    freq_from_start_stop_meas : bool
        infer frequency from start / stop intervals of individual
        measurements.
    freq_min_cov : float
        defines minimum number of measurements that need to correspond to the
        detected sampling frequency in the file within the specified tolerance
        range. Only applies if :attr:`ensure_correct_freq` is True. E.g. if a
        file contains 100 measurements and the most common frequency (as
        inferred from stop-start of each measurement) is daily. Then, if
        `freq_min_cov` is 0.75, it will be ensured that at least 75 of the
        measurements are daily (within +/- 5% tolerance), otherwise this file
        is discarded. Defaults to 0.

    Parameters
    ----------
    **args
        key / value pairs specifying any of the supported settings.
    """

    #: Names of options that correspond to reading filter constraints
    _FILTER_IDS = ["prefer_statistics", "wavelength_tol_nm"]

    def __init__(self, **args):
        self.prefer_statistics = ["arithmetic mean", "median"]
        # the last two are not part of the pyaerocom EBAS reader, but were needed to
        # get to the right data columns with the NILU provided PMF data
        self.ignore_statistics = [
            "percentile:15.87",
            "percentile:84.13",
            "uncertainty",
            "detection limit",
        ]

        self.wavelength_tol_nm = 50

        self.shift_wavelengths = True
        self.assume_default_ae_if_unavail = True

        self.check_correct_MAAP_wrong_wvl = False

        self.eval_flags = True

        self.keep_aux_vars = False

        self.convert_units = True
        self.try_convert_vmr_conc = True

        self.ensure_correct_freq = False
        self.freq_from_start_stop_meas = True
        self.freq_min_cov = 0.0

        self.update(**args)

    @property
    def filter_dict(self):
        d = {}
        for n in self._FILTER_IDS:
            d[n] = self[n]
        return d
