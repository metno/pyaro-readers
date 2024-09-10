import unittest
import urllib.request

import pyaro
import pyaro.timeseries

TEST_URL = "https://prod-actris-md.nilu.no/Version"
VOCABULARY_URL = "https://prod-actris-md.nilu.no/V"


class TestActrisEbasTimeSeriesReader(unittest.TestCase):
    engine = "actrisebas"

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
            "variables": {
                "include": [
                    "ozone mass concentration",
                ]
            },
            "stations": {"include": ["Birkenes II", "Jungfraujoch"]},
        }
        engine = pyaro.list_timeseries_engines()[self.engine]
        #
        with engine.open(
            filters=filters,
        ) as ts:
            self.assertGreaterEqual(len(ts.variables()), 1)

    def test_api_reading_pyaerocom_naming(self):
        # test access to the EBAS API
        filters = {
            "variables": {
                "include": [
                    "vmro3",
                ]
            },
            "stations": {"include": ["Birkenes II", "Jungfraujoch"]},
        }
        engine = pyaro.list_timeseries_engines()[self.engine]
        #
        with engine.open(
            filters=filters,
        ) as ts:
            self.assertGreaterEqual(len(ts.variables()), 1)

    #
    # def test_wrappers(self):
    #     engine = pyaro.list_timeseries_engines()["aeronetsunreader"]
    #     new_var_name = "od500aer"
    #     with VariableNameChangingReader(
    #         engine.open(self.file, filters=[]), {"AOD_500nm": new_var_name}
    #     ) as ts:
    #         self.assertEqual(ts.data(new_var_name).variable, new_var_name)
    #     pass
    #


if __name__ == "__main__":
    unittest.main()
