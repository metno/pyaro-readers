import unittest


class TestPyaroReaderPyaerocom(unittest.TestCase):
    engine = "actrisebas"

    station_filter = {
        "stations": {
            "include": ["Birkenes II", "Jungfraujoch", "Ispra", "Melpitz", "Westerland"]
        },
    }
    AERONETVAR = "od440aer"
    # ACTRISEBASVAR = "concso4t"
    # ACTRISEBASVAR = "concso4c"
    # ACTRISEBASVAR = "concprcpso4"
    ACTRISEBASVAR = "wetso4"
    # ACTRISEBASVAR = "prmm"
    # ACTRISEBASVAR = "vmro3"
    # ACTRISEBASVAR = "sc550aer"
    ACTRISEBASVARLIST = ["concso4t", "concso4c"]

    def test_pyaerocom_aeronet(self):
        # test reading via pyaerocom
        try:
            from pyaerocom.io.pyaro.pyaro_config import PyaroConfig
            from pyaerocom.io import ReadUngridded
        except ImportError:
            assert "pyaerocom not installed"
            return

        data_name = "aeronettest"
        data_id = "aeronetsunreader"
        url = "https://pyaerocom.met.no/pyaro-suppl/testdata/aeronetsun_testdata.csv"
        obsconfig = PyaroConfig(
            name=data_name,
            reader_id=data_id,
            filename_or_obj_or_url=url,
            filters={"variables": {"include": ["AOD_440nm"]}},
            name_map={"AOD_440nm": self.AERONETVAR},
        )
        reader = ReadUngridded(f"{data_name}")
        data = reader.read(vars_to_retrieve=self.AERONETVAR, configs=obsconfig)
        self.assertGreaterEqual(len(data.unique_station_names), 4)
        self.assertIn("Alta_Floresta", data.unique_station_names)

    def test_pyaerocom_actrisebas_single_var(self):
        # test reading via pyaerocom
        try:
            from pyaerocom.io.pyaro.pyaro_config import PyaroConfig
            from pyaerocom.io import ReadUngridded
        except ImportError:
            assert "pyaerocom not installed"
            return

        data_name = "PYARO_actrisebas"
        data_id = "actrisebas"
        station_filter = {
            "stations": {
                "include": [
                    "Schmucke",
                    "Birkenes II",
                    "Jungfraujoch",
                    "Ispra",
                    "Melpitz",
                    "Westerland",
                ]
            },
            "variables": {
                "include": [
                    self.ACTRISEBASVAR,
                ]
            },
            "time_bounds": {
                "startend_include": [("2019-01-01 00:00:00", "2020-12-31 00:00:00")]
            },
        }
        # needs to be the variable name for actrisebas
        url = self.ACTRISEBASVAR
        obsconfig = PyaroConfig(
            name=data_name,
            reader_id=data_id,
            filename_or_obj_or_url=url,
            filters=station_filter,
        )
        reader = ReadUngridded(f"{data_name}")
        data = reader.read(vars_to_retrieve=self.ACTRISEBASVAR, configs=obsconfig)
        self.assertGreaterEqual(len(data.unique_station_names), 2)
        self.assertIn("Schmucke", data.unique_station_names)
        self.assertIn(url, data.contains_vars)

    def test_pyaerocom_actrisebas_many_var(self):
        # test multi var reading via pyaerocom
        # not working properly atm as it's reading only one variable atm
        try:
            from pyaerocom.io.pyaro.pyaro_config import PyaroConfig
            from pyaerocom.io import ReadUngridded
        except ImportError:
            assert "pyaerocom not installed"
            return

        data_name = "PYARO_actrisebas"
        data_id = "actrisebas"
        station_filter = {
            "stations": {
                "include": [
                    "Birkenes II",
                    "Jungfraujoch",
                    "Ispra",
                    "Melpitz",
                    "Westerland",
                ]
            },
            "variables": {"include": ["concso4t", "concso4c"]},
        }
        # needs to be the variable name for actrisebas, but PyaroConfig wants this to a string and not a list
        # (the pydantic setup is too pedantic)
        url = self.ACTRISEBASVARLIST
        obsconfig = PyaroConfig(
            name=data_name,
            reader_id=data_id,
            filename_or_obj_or_url=url,
            filters=station_filter,
        )
        reader = ReadUngridded(f"{data_name}")
        data = reader.read(vars_to_retrieve=self.ACTRISEBASVAR, configs=obsconfig)
        self.assertGreaterEqual(len(data.unique_station_names), 4)
        self.assertIn("Ispra", data.unique_station_names)
        self.assertIn(url[0], data.contains_vars)
        # This does unfortunately not return the two variables asked for, but only the first:
        self.assertIn(url[1], data.contains_vars)


if __name__ == "__main__":
    unittest.main()
