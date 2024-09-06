import unittest
import urllib.request
import os

import pyaro
import pyaro.timeseries
from pyaro.timeseries.Wrappers import VariableNameChangingReader

TEST_URL = "https://prod-actris-md.nilu.no/Version"
VOCABULARY_URL = "https://prod-actris-md.nilu.no/V"
TEST_ZIP_URL = (
    "https://pyaerocom.met.no/pyaro-suppl/testdata/aeronetsun_testdata.csv.zip"
)
AERONETSUN_URL = "https://aeronet.gsfc.nasa.gov/data_push/V3/All_Sites_Times_Daily_Averages_AOD20.zip"


class TestActrisEbasTimeSeriesReader(unittest.TestCase):

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
        engine = pyaro.list_timeseries_engines()["actrisebas"]
        self.assertEqual(engine.url(), "https://github.com/metno/pyaro-readers")
        # just see that it doesn't fail
        engine.description()
        assert engine.args()

    def test_api_reading(self):
        # test access to the EBAS API
        engine = pyaro.list_timeseries_engines()["actrisebas"]
        with engine.open(var_name="ozone mass concentration", filters=[]) as ts:
            # test that the definitions file could be read properly
            self.assertGreaterEqual((len(ts._def_data)['variables'], 2))

    def test_api_reading_Birkenes(self):
        # test access to the EBAS API
        engine = pyaro.list_timeseries_engines()["actrisebas"]
        # sfilter = pyaro.timeseries.filters.get("stations", include=["Birkenes II"])
        with engine.open(vars_to_read="ozone mass concentration", filters=[], sites_to_read=["Birkenes II"]) as ts:
            # test that the definitions file could be read properly
            self.assertGreaterEqual((len(ts._def_data)['variables'], 2))

    # def test_stationfilter(self):
    #     engine = pyaro.list_timeseries_engines()["aeronetsunreader"]
    #     sfilter = pyaro.timeseries.filters.get("stations", exclude=["Cuiaba"])
    #     with engine.open(
    #         self.file, filters=[sfilter], tqdm_desc="test_stationfilter"
    #     ) as ts:
    #         count = 0
    #         for var in ts.variables():
    #             count += len(ts.data(var))
    #         self.assertEqual(count, 48775)
    #         self.assertEqual(len(ts.stations()), 3)
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
    # def test_variables_filter(self):
    #     engine = pyaro.list_timeseries_engines()["aeronetsunreader"]
    #     new_var_name = "od550aer"
    #     vfilter = pyaro.timeseries.filters.get(
    #         "variables", reader_to_new={"AOD_550nm": new_var_name}
    #     )
    #     with engine.open(
    #         self.file, filters=[vfilter], tqdm_desc="test_variables_filter"
    #     ) as ts:
    #         self.assertEqual(ts.data(new_var_name).variable, new_var_name)


if __name__ == "__main__":
    unittest.main()
