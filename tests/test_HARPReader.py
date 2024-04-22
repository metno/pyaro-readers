import unittest
from src.pyaro_readers.harpreader.harpreader import *
import pyaro
import pyaro.timeseries


class TestHARPReader(unittest.TestCase):
    engine = "????"

    def test_2read(self):
        with pyaro.open_timeseries(self.engine) as ts:
            data = ts.data("sulphur_dioxide_in_air")
            self.assertIn("AM0001", data.stations)
            self.assertGreater(np.sum(data.values), 10000)
            self.assertEqual(data.units, "ug")

    def test_3read(self):
        with pyaro.open_timeseries(
            self.engine,
            resolution="daily",
            filters={
                "stations": {"include": ["NO0002"]},
            },  # Birkenes2
        ) as ts:
            data = ts.data("sulphur_dioxide_in_air")
            self.assertIn("NO0002", data.stations)
            self.assertGreater(len(data), 360)
            self.assertEqual(data.units, "ug")
            self.assertEqual(
                len(data.values[data.values > 4]), 1
            )  # one day (21.05. with extreme SO2)
