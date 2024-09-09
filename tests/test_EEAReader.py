import unittest
import os
from pathlib import Path

import pyaro
import pyaro.timeseries


class TestEEATimeSeriesReader(unittest.TestCase):
    engine = "eeareader"

    file = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "testdata",
        "EEA",
    )

    test_vars = ["PM10", "SO2"]

    testdata_dir = Path(
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "testdata", "EEA")
    )

    def test_0engine(self):
        self.assertIn(self.engine, pyaro.list_timeseries_engines())

    def test_1open_files(self):
        with pyaro.open_timeseries(
            self.engine,
            self.testdata_dir,
            filters={"variables": {"include": ["PM10", "SO2"]}},
        ) as ts:
            self.assertGreaterEqual(len(ts.variables()), 2)
            self.assertGreaterEqual(len(ts.stations()), 2)
            for var in ts.variables():
                assert var in self.test_vars


if __name__ == "__main__":
    unittest.main()
