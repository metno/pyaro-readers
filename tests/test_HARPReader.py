import unittest
import pyaro
import pyaro.timeseries
import cf_units
import os


class TestHARPReader(unittest.TestCase):
    engine = "harp"

    file = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "testdata",
        "sinca-surface-220-999999-001.nc",
    )

    testdata_dir = (
        "/lustre/storeB/project/aerocom/aerocom1/AEROCOM_OBSDATA/SINCA/aggregated/"
    )
    test_vars = ["PM10_density", "CO_volume_mixing_ratio", "PM2p5_density"]
    test_units = ["ug m-3", "ppm", "ug m-3"]

    def test_1read(self):
        with pyaro.open_timeseries(
            self.engine,
            self.file,
            vars_to_read=self.test_vars,
        ) as ts:
            for _v_idx, var in enumerate(self.test_vars):
                data = ts.data(var)
                self.assertGreater(len(data), 10000)
                assert isinstance(data.units, str)
                self.assertEqual(
                    data.units, str(cf_units.Unit(self.test_units[_v_idx]))
                )
                self.assertGreaterEqual(len(ts.variables()), 2)
                self.assertGreaterEqual(len(ts.stations()), 1)

                self.assertIn("revision", ts.metadata())
                self.assertGreaterEqual(int(ts.metadata()["revision"]), 240326150136)

    def test_2open_directory(self):
        if os.path.exists(self.testdata_dir):
            with pyaro.open_timeseries(
                self.engine, self.testdata_dir, filters=[], vars_to_read=self.test_vars
            ) as ts:
                for _v_idx, var in enumerate(self.test_vars):
                    data = ts.data(var)
                    assert isinstance(data.units, str)
                self.assertGreaterEqual(len(ts.variables()), 2)
                self.assertGreaterEqual(len(ts.stations()), 7)

                self.assertIn("revision", ts.metadata())

        else:
            pass


if __name__ == "__main__":
    unittest.main()
