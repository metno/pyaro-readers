import unittest
import os
from pathlib import Path

import pyaro
import pyaro.timeseries
import numpy as np

from pyaro_readers.eeareader import EEATimeseriesReader


class TestEEATimeSeriesReader(unittest.TestCase):
    engine = "eeareader"

    file = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "testdata",
        "EEA",
    )

    test_vars = ["PM10", "SO2"]

    testdata_dir = Path(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "testdata",
            "EEA",
            "catalog.parquet",
        )
    )

    def test_0engine(self):
        self.assertIn(self.engine, pyaro.list_timeseries_engines())

    def test_1open_files(self):
        with pyaro.open_timeseries(
            self.engine,
            self.testdata_dir,
        ) as ts:
            self.assertGreaterEqual(len(ts.variables()), 2)
            self.assertGreaterEqual(len(ts.stations()), 2)
            self.assertTrue(set(self.test_vars).issubset(ts.variables()))

    def test_eea_reader(self):
        filters = pyaro.timeseries.FilterCollection(
            {
                "time_bounds": {
                    "start_include": [("2019-01-01 00:00:00", "2025-12-24 00:00:00")]
                },
                "stations": {
                    "exclude": ["NO/SPO_NO0151A_8_4768", "NO/SPO_NO0111A_9_1691"]
                },
                "countries": {"include": ["NO", "LU"]},
            }
        )

        # If PPI is available one can use the following:
        # "/lustre/storeB/project/aerocom/aerocom1/AEROCOM_OBSDATA/EEA-AQDS/download",
        reader = EEATimeseriesReader(
            self.testdata_dir,
            filters=filters,
        )

        stations = reader.stations()
        assert len(stations) == 4

        variables = reader.variables()
        assert set(variables) == {"PM10", "SO2"}

        expected_counts = {
            "PM10": 21904,
            "SO2": 18857,
        }
        for species in self.test_vars:
            data = reader.data(species)
            assert len(data) == expected_counts[species]
            _ = data.values
            alts = data.altitudes
            self.assertFalse(np.any(np.isnan(alts)))


if __name__ == "__main__":
    unittest.main()
