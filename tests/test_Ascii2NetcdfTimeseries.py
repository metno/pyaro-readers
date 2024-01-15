import unittest

import pyaro
import pyaro.timeseries

EBAS_URL = "/disk1/tmp/NILU/"

class TestAscii2NetcdfTimeSeriesReader(unittest.TestCase):
    engine = "ascii2netcdf"
    def test_engine(self):
        self.assertIn(self.engine, pyaro.list_timeseries_engines())

    def test_open(self):
        with pyaro.open_timeseries(
            self.engine,
            EBAS_URL,
            resolution="daily",
            filters=[]
        ) as ts:
            self.assertGreater(len(ts.variables()), 0)
            self.assertGreater(len(ts.stations()), 0)


