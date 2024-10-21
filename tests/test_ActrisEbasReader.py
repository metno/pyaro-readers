import unittest
import urllib.request

import pyaro
import pyaro.timeseries
from pyaro.timeseries.Wrappers import VariableNameChangingReader

TEST_URL = "https://prod-actris-md.nilu.no/Version"
VOCABULARY_URL = "https://prod-actris-md.nilu.no/V"


class TestActrisEbasTimeSeriesReader(unittest.TestCase):
    engine = "actrisebas"

    station_filter = {
        "stations": {
            "include": ["Birkenes II", "Jungfraujoch", "Ispra", "Melpitz", "Westerland"]
        },
    }
    # vars_to_read = ["ozone mass concentration"]
    # vars_to_read = ["aerosol particle sulphate mass concentration"]
    vars_to_read = ["aerosol particle elemental carbon mass concentration"]
    # pyaerocom_vars_to_read = ["conco3"]
    pyaerocom_vars_to_read = ["vmro3"]
    # pyaerocom_vars_to_read = ["concso4t"]

    def test_api_online(self, url=TEST_URL):
        try:
            req = urllib.request.Request(TEST_URL, method="HEAD")
            resp = urllib.request.urlopen(req)
            resp.url
            return True
        except:
            return False

    # def test_vocabulary(self, url=TEST_URL):
    #     try:
    #         req = urllib.request.Request(TEST_URL, method="HEAD")
    #         resp = urllib.request.urlopen(req)
    #         resp.url
    #         return True
    #     except:
    #         return False
    #

    def test_init(self):
        engine = pyaro.list_timeseries_engines()[self.engine]
        self.assertEqual(engine.url(), "https://github.com/metno/pyaro-readers")
        # just see that it doesn't fail
        engine.description()
        assert engine.args()

    def test_flag_list_online(self):
        engine = pyaro.list_timeseries_engines()[self.engine]

        self.assertEqual(engine.url(), "https://github.com/metno/pyaro-readers")
        # just see that it doesn't fail
        engine.description()
        assert engine.args()

    # def test_api_reading(self):
    #     # test access to the EBAS API
    #     filters={"variables": {"include": ["ozone mass concentration", ]}}
    #     engine = pyaro.list_timeseries_engines()[self.engine]
    #     with engine.open(filters=filters) as ts:
    #         # test that the definitions file could be read properly
    #         self.assertGreaterEqual(len(ts.variables()), 2)
    #
    def test_api_reading_small_data_set(self):
        # test access to the EBAS API
        filters = {
            "stations": {"include": ["Birkenes II", "Jungfraujoch"]},
            # "variables": {
            #     "include": self.vars_to_read,
            # },
        }
        engine = pyaro.list_timeseries_engines()[self.engine]
        read_obj = engine.open(
            filters=self.station_filter, vars_to_read=self.vars_to_read
        )
        with read_obj.read() as ts:
            self.assertGreaterEqual(len(ts.variables()), 1)
            self.assertGreaterEqual(len(read_obj.stations()), 2)
            self.assertGreaterEqual(len(read_obj._data[read_obj.variables()[0]]), 1000)
            self.assertGreaterEqual(len(read_obj.data(read_obj.variables()[0])), 1000)
            self.assertGreaterEqual(len(read_obj.variables()), 1)
            self.assertIn("revision", read_obj.metadata())

    # def test_api_reading_small_data_set_without_cm(self):
    #     # test access to the EBAS API
    #     filters = {
    #         "stations": {"include": ["Birkenes II", "Jungfraujoch"]},
    #         # "variables": {
    #         #     "include": self.vars_to_read,
    #         # },
    #     }
    #     engine = pyaro.list_timeseries_engines()[self.engine]
    #     read_obj = engine.open(
    #         filters=self.station_filter, vars_to_read=self.vars_to_read
    #     )
    #     read_obj.read()
    #     self.assertGreaterEqual(len(read_obj.variables()), 1)
    #     self.assertGreaterEqual(len(read_obj.stations()), 2)
    #     self.assertGreaterEqual(len(read_obj._data[read_obj.variables()[0]]), 1000)
    #     self.assertGreaterEqual(len(read_obj.data(read_obj.variables()[0])), 1000)
    #     self.assertGreaterEqual(len(read_obj.variables()), 1)
    #     self.assertIn("revision", read_obj.metadata())

    def test_api_reading_pyaerocom_naming(self):
        # test access to the EBAS API
        filters = {
            "stations": {"include": ["Birkenes II", "Jungfraujoch"]},
            # "variables": {
            #     "include": self.vars_to_read,
            # },
        }
        # test variable by variable
        for _var in self.pyaerocom_vars_to_read:
            engine = pyaro.list_timeseries_engines()[self.engine]
            read_obj = engine.open(filters=self.station_filter, vars_to_read=[_var])
            with read_obj.read() as ts:
                self.assertGreaterEqual(len(ts.variables()), 1)
                self.assertGreaterEqual(len(ts.stations()), 2)
                self.assertGreaterEqual(len(ts._data[read_obj.variables()[0]]), 1000)
                self.assertGreaterEqual(len(ts.data(read_obj.variables()[0])), 1000)
                self.assertGreaterEqual(len(ts.variables()), 1)
                self.assertIn("revision", ts.metadata())


    #
    # #
    # def test_wrappers(self):
    #     engine = pyaro.list_timeseries_engines()[self.engine]
    #     new_var_name = "vmro3"
    #     with VariableNameChangingReader(
    #             engine.open(vars_to_read=self.vars_to_read, filters=self.station_filter),
    #             {self.vars_to_read[0]: new_var_name}
    #     ) as ts:
    #         self.assertEqual(ts.data(new_var_name).variable, new_var_name)
    #     pass
    # #


if __name__ == "__main__":
    unittest.main()
