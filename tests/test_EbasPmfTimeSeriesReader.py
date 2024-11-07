import unittest
import os

import pyaro
import pyaro.timeseries
from pyaro_readers.nilupmfebas.ebas_nasa_ames import read_ebas_flags_file


class TestPMFEBASTimeSeriesReader(unittest.TestCase):
    engine = "nilupmfebas"

    file = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "testdata",
        "PMF_EBAS",
        "SI0008R.20171129230000.20210615130447.low_vol_sampler..pm25.32d.1d.SI01L_ARSO_pm25vz_2.SI01L_ARSO_ECOC_1.lev2.nas",
    )

    test_vars = [
        "#elemental_carbon#ug C m-3",
        "#galactosan#ng m-3",
        "#levoglucosan#ng m-3",
        "#mannosan#ng m-3",
        "#organic_carbon#ug C m-3",
        "#total_carbon#ug C m-3",
        "pm1#elemental_carbon#ug C m-3",
        "pm1#levoglucosan#ng m-3",
        "pm1#organic_carbon#ug C m-3",
        "pm1#total_carbon#ug C m-3",
        "pm10#elemental_carbon#ug C m-3",
        "pm10#galactosan#ng m-3",
        "pm10#levoglucosan#ng m-3",
        "pm10#mannosan#ng m-3",
        "pm10#organic_carbon#ug C m-3",
        "pm10#pressure#hPa",
        "pm10#temperature#K",
        "pm10#total_carbon#ug C m-3",
        "pm10_pm25#organic_carbon#ug C m-3",
        "pm10_pm25#total_carbon#ug C m-3",
        "pm25#elemental_carbon#ug C m-3",
        "pm25#galactosan#ng m-3",
        "pm25#levoglucosan#ng m-3",
        "pm25#mannosan#ng m-3",
        "pm25#organic_carbon#ug C m-3",
        "pm25#total_carbon#ug C m-3",
    ]

    testdata_dir = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "testdata", "PMF_EBAS"
    )

    def test_0engine(self):
        self.assertIn(self.engine, pyaro.list_timeseries_engines())

    def test_1open_single_file(self):
        with pyaro.open_timeseries(self.engine, self.file, filters=[]) as ts:
            self.assertGreaterEqual(len(ts.variables()), 1)
            for var in ts.variables():
                assert var in self.test_vars
            self.assertEqual(len(ts.stations()), 1)

            self.assertIn("revision", ts.metadata())

    def test_2open_directory(self):
        with pyaro.open_timeseries(self.engine, self.testdata_dir, filters=[]) as ts:
            self.assertGreaterEqual(len(ts.variables()), 1)
            for var in ts.variables():
                assert var in self.test_vars

            self.assertIn("revision", ts.metadata())

    def test_3open_ebascsvfile(self):
        dummy = read_ebas_flags_file(None)
        assert isinstance(dummy, dict)
        assert isinstance(dummy["valid"], dict)
        assert isinstance(dummy["info"], dict)
        assert isinstance(dummy["vals"], dict)


if __name__ == "__main__":
    unittest.main()
