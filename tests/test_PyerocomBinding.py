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

    # Try testing the pyaerocom binding if pyaerocom is installed
    try:
        from pyaerocom.io import ReadUngridded
        pyaerocom_installed_flag = True
    except ImportError:
        pyaerocom_installed_flag = False
        pass

    AERONETVAR = "od440aer"


    def test_pyaerocom_aeronet(self):
        # test reading via pyaerocom
        try:
            from pyaerocom.io.pyaro.pyaro_config import PyaroConfig
            from pyaerocom.io import ReadUngridded
        except ImportError:
            assert("pyaerocom not installed")
            return

        data_name = "aeronettest"
        data_id = "aeronetsunreader"
        url = "https://pyaerocom.met.no/pyaro-suppl/testdata/aeronetsun_testdata.csv"
        obsconfig = PyaroConfig(
            name=data_name,
            data_id=data_id,
            filename_or_obj_or_url=url,
            filters={"variables": {"include": ["AOD_440nm"]}},
            name_map={"AOD_440nm": self.AERONETVAR},
        )
        reader = ReadUngridded(f"{data_name}")
        data = reader.read(vars_to_retrieve=self.AERONETVAR, configs=obsconfig)
        self.assertGreaterEqual(len(data.unique_station_names), 4)
        self.assertIn("Alta_Floresta", data.unique_station_names)


    def test_api_reading_pyaerocom_naming(self):
        # test access to the EBAS API
        # test variable by variable
        for _var in self.pyaerocom_vars_to_read:
            engine = pyaro.list_timeseries_engines()[self.engine]
            with engine.open(filters=self.station_filter, vars_to_read=[_var]) as ts:
                self.assertGreaterEqual(len(ts.variables()), 1)
                self.assertGreaterEqual(len(ts.stations()), 2)
                self.assertGreaterEqual(len(ts._data[ts.variables()[0]]), 1000)
                self.assertGreaterEqual(len(ts.data(ts.variables()[0])), 1000)
                self.assertIn("revision", ts.metadata())



if __name__ == "__main__":
    unittest.main()
