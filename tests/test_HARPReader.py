import unittest
import pyaro
import pyaro.timeseries
import cfunits


class TestHARPReader(unittest.TestCase):
    engine = "harp"

    def test_1read(self):
        with pyaro.open_timeseries(
            self.engine,
            "tests/testdata/sinca-surface-157-999999-001.nc",
        ) as ts:
            data = ts.data("CO_volume_mixing_ratio")

            self.assertGreater(len(data), 10000)
            self.assertEqual(data.units, cfunits.Units("ppm"))
