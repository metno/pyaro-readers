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
        "stations": {"include": ["Birkenes II", "Jungfraujoch"]},
    }
    vars_to_read = ["ozone mass concentration"]

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
        #
        with engine.open(
                filters=filters,
                vars_to_read=self.vars_to_read,
        ) as ts:
            self.assertGreaterEqual(len(ts.variables()), 1)
            self.assertEqual(len(ts.stations()), 2)
            self.assertGreaterEqual(len(ts._data[ts.variables()[0]]), 1000)
            self.assertGreaterEqual(len(ts.data(ts.variables()[0])), 1000)

            self.assertIn("revision", ts.metadata())

    # def test_api_reading_pyaerocom_naming(self):
    #     # test access to the EBAS API
    #     filters = {
    #         "variables": {
    #             "include": [
    #                 "vmro3",
    #             ]
    #         },
    #         "stations": {"include": ["Birkenes II", "Jungfraujoch"]},
    #     }
    #     engine = pyaro.list_timeseries_engines()[self.engine]
    #     #
    #     with engine.open(
    #         filters=filters,
    #             vars_to_read=["vmro3"],
    #     ) as ts:
    #         self.assertGreaterEqual(len(ts.variables()), 1)
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
