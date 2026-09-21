import unittest
import logging
import os
import pickle
import pyaro
import pyaro.timeseries

try:
    from pyaerocom.io.pyaro.pyaro_config import PyaroConfig
    from pyaerocom.io import ReadUngridded
except ImportError:
    assert "pyaerocom not installed"

logger = logging.getLogger(__name__)

TEST_PICKL_FILE = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "testdata",
    "PYARO_actrisebas_vmrco.pkl",
)

TEST_PICKL_FILE2 = "/home/jang/MyPyaerocom/_cache/jang/EBASMC_vmrco.pkl"
TEST_PICKL_FILE3 = "/home/jang/MyPyaerocom/_cache/jang/ACTRIS-EBAS-d-tc_vmro3.pkl"


class TestCaching2Pyaro(unittest.TestCase):
    engine = "netcdf_rw"
    infile = TEST_PICKL_FILE
    outfile = infile.replace(".pkl", ".nc")

    def test_0engine(self):
        self.assertIn(self.engine, pyaro.list_timeseries_engines())

    def test_1caching2pyaro(self):
        # test converting a pyaerocom cache file to a netcdf using pyaro's netcdf_rw engine

        # from pyaerocom.io.cachehandler_ungridded import CacheHandlerUngridded
        # ch = CacheHandlerUngridded()
        # if ch.check_and_load(file_name, cache_dir=data_dir):
        #     return ch.loaded_data[file_name]
        logging.info(f"reading infile: {self.infile}")
        with open(TEST_PICKL_FILE, "rb") as inhandle:
            meta_data = pickle.load(inhandle)
            data = pickle.load(inhandle)

        assert "pyaro_config" in meta_data
        assert data.station_name

        logging.info(f"writing outfile: {self.outfile}")

        with pyaro.open_timeseries(
            self.engine, self.outfile, mode="w", filters=[]
        ) as ts_rw:
            for _var in data.contains_vars:
                data_unit = data.metadata[0]["var_info"][_var]["units"]
                data = pyaro.timeseries.NpStructuredData(_var, data_unit)
                for _station_data in data:
                    assert data


if __name__ == "__main__":
    unittest.main()
