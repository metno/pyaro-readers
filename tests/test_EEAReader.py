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


def test_eea_reader2():
    from pyaro_readers.eeareader import EEATimeseriesReader
    import pyaro.timeseries

    filters = pyaro.timeseries.FilterCollection(
        {
            # "time_bounds": {"start_include": [("2023-01-01 00:00:00", "2023-12-24 00:00:00")]},
            "stations": {
                "exclude": ["GB/GB_SamplingPoint_61718", "GB/GB_SamplingPoint_99"]
            },
            "countries": {"include": ["UK"]},
        }
    )

    reader = EEATimeseriesReader(
        "/lustre/storeB/project/aerocom/aerocom1/AEROCOM_OBSDATA/EEA-AQDS/download",
        filters=filters,
        enable_progressbar=True,
    )

    _ = reader.stations()
    eea_variables = reader.variables()
    known_variables = {"PM2.5", "PM10", "NO2"}
    assert known_variables.issubset(eea_variables)

    data = reader.data("PM2.5")
    _ = data.altitudes
    _ = data.values


if __name__ == "__main__":
    unittest.main()
