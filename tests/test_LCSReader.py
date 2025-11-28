import os
import unittest
import logging

from pathlib import Path

import pyaro
import pyaro.timeseries

from pyaro_readers.lcsreader import LCSReader


class TestLCSReader(unittest.TestCase):
    engine = "lcsreader"

    testdata_dir = Path(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "testdata",
            "LCS",
        )
    )

    testdata_corr = testdata_dir / "corrected_data.parquet"
    testdata_raw = testdata_dir / "raw_data.parquet"

    test_vars = ["PM25"]

    def test_engine_exist(self):
        self.assertIn(self.engine, pyaro.list_timeseries_engines())

    def test_all_open_files(self):
        with pyaro.open_timeseries(
            self.engine,
            self.testdata_corr,
            filters={},
            min_quality=0,
        ) as ts:
            self.assertEqual(len(ts.variables()), 1)
            self.assertEqual(len(ts.stations()), 3)
            self.assertEqual(set(self.test_vars), set(ts.variables()))

        with pyaro.open_timeseries(
            self.engine,
            self.testdata_raw,
            filters={},
            min_quality=0,
        ) as ts:
            self.assertEqual(len(ts.variables()), 1)
            self.assertEqual(len(ts.stations()), 3)
            self.assertEqual(set(self.test_vars), set(ts.variables()))

    def test_networks(self):
        reader = LCSReader(self.testdata_corr, network="PA", filters={})

        stations = reader.stations()
        assert len(stations) == 2

        reader = LCSReader(self.testdata_corr, network="SC", filters={})

        stations = reader.stations()
        assert len(stations) == 1

    def test_quality(self):

        reader_low = LCSReader(self.testdata_corr, min_quality=1, filters={})

        reader = LCSReader(self.testdata_corr, min_quality=2, filters={})

        data_low = reader_low.data(self.test_vars[0])
        data = reader.data(self.test_vars[0])
        assert len(data_low) > len(data)


if __name__ == "__main__":
    unittest.main()
