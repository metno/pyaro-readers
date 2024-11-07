import unittest
import os

import pyaro
import pyaro.timeseries


class TestPMFEBASTimeSeriesReader(unittest.TestCase):
    engine = "nilupmfabsorption"

    file = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "testdata",
        "PMF_Absorption",
        "Zeppelin_absorption_20171201_3mo_PMF_lev3.nas",
    )

    test_vars = ["Babs_bb", "Babs_ff", "eBC_bb", "eBC_ff"]

    testdata_dir = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "testdata", "PMF_Absorption"
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
            self.assertGreaterEqual(int(ts.metadata()["revision"]), 180301000000)

    def test_2open_directory(self):
        with pyaro.open_timeseries(self.engine, self.testdata_dir, filters=[]) as ts:
            self.assertGreaterEqual(len(ts.variables()), 1)
            for var in ts.variables():
                assert var in self.test_vars

            self.assertIn("revision", ts.metadata())
            self.assertGreaterEqual(int(ts.metadata()["revision"]), 180301000000)


if __name__ == "__main__":
    unittest.main()
