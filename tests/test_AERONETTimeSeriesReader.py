import unittest
import os

import pyaro
import pyaro.timeseries
from pyaro.timeseries.Wrappers import VariableNameChangingReader

TEST_URL = "https://pyaerocom.met.no/pyaro-suppl/testdata/aeronetsun_testdata.csv"
TEST_ZIP_URL = (
    "https://pyaerocom.met.no/pyaro-suppl/testdata/aeronetsun_testdata.csv.zip"
)


class TestAERONETTimeSeriesReader(unittest.TestCase):
    file = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "testdata",
        "aeronetsun_testdata.csv",
    )

    def test_dl_data_unzipped(self):
        engine = pyaro.list_timeseries_engines()["aeronetsunreader"]
        with engine.open(TEST_URL, filters=[], fill_country_flag=False, tqdm_desc="test_dl_data_unzipped") as ts:
            count = 0
            for var in ts.variables():
                count += len(ts.data(var))
            self.assertEqual(count, 49965)
            self.assertEqual(len(ts.stations()), 4)

    def test_dl_data_zipped(self):
        engine = pyaro.list_timeseries_engines()["aeronetsunreader"]
        with engine.open(TEST_ZIP_URL, filters=[], fill_country_flag=False, tqdm_desc="test_dl_data_zipped") as ts:
            count = 0
            for var in ts.variables():
                count += len(ts.data(var))
            self.assertEqual(count, 49965)
            self.assertEqual(len(ts.stations()), 4)

    def test_init(self):
        engine = pyaro.list_timeseries_engines()["aeronetsunreader"]
        self.assertEqual(engine.url(), "https://github.com/metno/pyaro-readers")
        # just see that it doesn't fail
        engine.description()
        engine.args()
        with engine.open(self.file, filters=[], fill_country_flag=True, tqdm_desc="test_init") as ts:
            count = 0
            for var in ts.variables():
                count += len(ts.data(var))
            self.assertEqual(count, 49965)
            self.assertEqual(len(ts.stations()), 4)

    def test_stationfilter(self):
        engine = pyaro.list_timeseries_engines()["aeronetsunreader"]
        sfilter = pyaro.timeseries.filters.get("stations", exclude=["Cuiaba"])
        with engine.open(self.file, filters=[sfilter], tqdm_desc="test_stationfilter") as ts:
            count = 0
            for var in ts.variables():
                count += len(ts.data(var))
            self.assertEqual(count, 48775)
            self.assertEqual(len(ts.stations()), 3)

    def test_wrappers(self):
        engine = pyaro.list_timeseries_engines()["aeronetsunreader"]
        new_var_name = "od500aer"
        with VariableNameChangingReader(
            engine.open(self.file, filters=[]), {"AOD_500nm": new_var_name}
        ) as ts:
            self.assertEqual(ts.data(new_var_name).variable, new_var_name)
        pass

    def test_variables_filter(self):
        engine = pyaro.list_timeseries_engines()["aeronetsunreader"]
        new_var_name = "od550aer"
        vfilter = pyaro.timeseries.filters.get(
            "variables", reader_to_new={"AOD_550nm": new_var_name}
        )
        with engine.open(self.file, filters=[vfilter], tqdm_desc="test_variables_filter") as ts:
            self.assertEqual(ts.data(new_var_name).variable, new_var_name)


if __name__ == "__main__":
    unittest.main()
