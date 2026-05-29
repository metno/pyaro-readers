import os
import unittest
import logging

from pathlib import Path

import pyaro
import pyaro.timeseries

from pyaro_readers.ghostreader import GHOSTReader


class TestGHOSTReader(unittest.TestCase):
    engine = "ghostreader"

    testdata_dir = Path(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "testdata",
            "GHOST",
        )
    )

    test_vars = ["sconcso4", "pm2p5", "sconcno2"]

    limited_test_vars = ["sconcso4"]
    variable_filter = pyaro.timeseries.Filter.VariableNameFilter(
        {}, limited_test_vars, []
    )

    time_filter = pyaro.timeseries.Filter.TimeBoundsFilter(
        [("2009-01-01 00:00:00", "2022-12-31 23:59:59")]
    )

    def test_engine_exist(self):
        pyaro.list_timeseries_engines.cache_clear()
        self.assertIn(self.engine, pyaro.list_timeseries_engines())

    def test_all_open_files(self):
        pyaro.list_timeseries_engines.cache_clear()
        with pyaro.open_timeseries(
            self.engine,
            self.testdata_dir,
            filters={},
            frequency="monthly",
            compressed=True,
            networks=["EBAS-EMEP", "US_EPA_AQS"],
        ) as ts:
            self.assertGreaterEqual(len(ts.variables()), 2)

            self.assertGreaterEqual(len(ts.stations()), 1446)
            self.assertEqual(set(self.test_vars), set(ts.variables()))

    def test_networks(self):
        reader = GHOSTReader(
            self.testdata_dir,
            networks=["EBAS-EMEP"],
            filters={},
            compressed=True,
            frequency="monthly",
        )

        stations = reader.stations()

        assert len(stations) >= 65

        reader = GHOSTReader(
            self.testdata_dir,
            networks=["US_EPA_AQS"],
            filters={},
            compressed=True,
            frequency="monthly",
        )

        stations = reader.stations()
        assert len(stations) >= 1381

    def test_uncompressed(self):
        reader = GHOSTReader(
            self.testdata_dir,
            networks=["EBAS-EMEP"],
            filters={},
            compressed=False,
            frequency="monthly",
        )

        files = reader.get_file_list()

        assert len(files) == 0

    def test_filtered(self):
        area_filter = [
            "rural",
            "rural-near_city",
            "rural-regional",
            "rural-remote",
        ]

        reader_no_filter = GHOSTReader(
            self.testdata_dir,
            networks=["US_EPA_AQS"],
            filters={},
            compressed=True,
            frequency="monthly",
        )

        reader_filter = GHOSTReader(
            self.testdata_dir,
            networks=["US_EPA_AQS"],
            filters={},
            area_classifications=area_filter,
            compressed=True,
            frequency="monthly",
        )

        assert len(reader_no_filter.stations()) > len(reader_filter.stations())

    def test_filtered_concso4(self):
        area_filter = [
            "rural",
            "rural-near_city",
            "rural-regional",
            "rural-remote",
        ]
        filter = [self.variable_filter]
        filter_time = [self.variable_filter, self.time_filter]
        # reader_no_filter = GHOSTReader(
        #     self.testdata_dir,
        #     networks=["EBAS-EMEP"],
        #     filters=filter,
        #     compressed=True,
        #     frequency="monthly",
        # )

        reader_filter = GHOSTReader(
            self.testdata_dir,
            networks=["EBAS-EMEP"],
            filters=filter_time,
            area_classifications=area_filter,
            compressed=True,
            frequency="monthly",
        )

        assert len(reader_filter.stations()) > 0
        blubb = reader_filter.stations()
        bla = reader_filter.data(self.limited_test_vars[0])
        assert len(reader_filter.stations()) > 0

        # assert len(reader_no_filter.stations()) > len(reader_filter.stations())

    def test_meta_keys(self):
        reader = GHOSTReader(
            self.testdata_dir,
            networks=["EBAS-EMEP"],
            filters={},
            compressed=True,
            frequency="monthly",
        )

        meta_keys = reader.META_KEYS

        assert isinstance(meta_keys, list)
        assert len(meta_keys) > 0


if __name__ == "__main__":
    unittest.main()
