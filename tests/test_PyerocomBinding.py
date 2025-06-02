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

    HARPVAR = "concpm10"
    HARPVARLIST = ["concpm10", "concpm25", "vmro3", "vmrno2"]
    STARTYEAR = 2019
    STOPYEAR = 2024

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
            # "stations": {
            #     "include": [
            #         "Schmucke",
            #         "Birkenes II",
            #         "Jungfraujoch",
            #         "Ispra",
            #         "Melpitz",
            #         "Westerland",
            #     ]
            # },
            "variables": {"include": [self.ACTRISEBASVAR, ]},
            "time_bounds":{"startend_include": [("2019-01-01 00:00:00", "2020-12-31 00:00:00")]}
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

    def test_pyaerocom_harp_single_var(self):
        # test reading via pyaerocom
        try:
            from pyaerocom.io.pyaro.pyaro_config import PyaroConfig
            from pyaerocom.io import ReadUngridded
        except ImportError:
            assert "pyaerocom not installed"
            return

        data_name = "SINCA"
        data_id = "harp"
        station_filter = {
            # "stations": {
            #     "include": [
            #         "Schmucke",
            #         "Birkenes II",
            #         "Jungfraujoch",
            #         "Ispra",
            #         "Melpitz",
            #         "Westerland",
            #     ]
            # },
            "variables": {"include": [self.ACTRISEBASVAR, ]},
            "time_bounds":{"startend_include": [("2019-01-01 00:00:00", "2020-12-31 00:00:00")]}
        }
        # needs to be the variable name for actrisebas
        # url = self.ACTRISEBASVAR
        # obsconfig = PyaroConfig(
        #     name=data_name,
        #     reader_id=data_id,
        #     filename_or_obj_or_url=url,
        #     filters=station_filter,
        # )

        sinca_config = PyaroConfig(
            name="SINCA",
            reader_id="harp",
            filename_or_obj_or_url="/lustre/storeB/project/aerocom/aerocom1/AEROCOM_OBSDATA/SINCA/aggregated/",
            filters={
                "variables": {
                    "include": ["PM10_density", "PM2p5_density", "O3_volume_mixing_ratio", "NO2_volume_mixing_ratio"]},
                "time_bounds": {"startend_include": [(f"{self.STARTYEAR}-01-01 00:00:00", f"{self.STOPYEAR}-01-01 00:00:00")], },
            },
            name_map={"PM10_density": "concpm10", "PM2p5_density": "concpm25", "O3_volume_mixing_ratio": "vmro3",
                      "NO2_volume_mixing_ratio": "vmrno2"},
        )

        obsconfig = PyaroConfig(name=data_name,
                                   reader_id=data_id,
                                   filename_or_obj_or_url="/lustre/storeB/project/aerocom/aerocom1/AEROCOM_OBSDATA/SINCA/aggregated/",
                                   filters={
                                       # "variables": {"include": ["PM10_density", "PM2p5_density", "O3_volume_mixing_ratio", "NO2_volume_mixing_ratio"]},
                                       "variables": {"include": ["PM10_density"]},
                                       # "time_bounds": {"startend_include": [(f"{STARTYEAR}-01-01 00:00:00", f"{STOPYEAR}-01-01 00:00:00")],},
                                   },
                                   name_map={"PM10_density": "concpm10",
                                             # "PM2p5_density": "concpm25",
                                             # "O3_volume_mixing_ratio": "vmro3",
                                             # "NO2_volume_mixing_ratio": "vmrno2",
                                             }, )
        reader = ReadUngridded(f"{data_name}")
        data = reader.read(vars_to_retrieve=self.HARPVAR, configs=sinca_config)
        self.assertGreaterEqual(len(data.unique_station_names), 2)
        # self.assertIn("Schmucke", data.unique_station_names)
        # self.assertIn(url, data.contains_vars)

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
