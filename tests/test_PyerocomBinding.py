import unittest
import logging

logger = logging.getLogger(__name__)


class TestPyaroReaderPyaerocom(unittest.TestCase):
    engine = "actrisebas"

    station_filter = {
        "stations": {
            "include": ["Birkenes II", "Jungfraujoch", "Ispra", "Melpitz", "Westerland"]
        },
    }
    AERONETVAR = "od440aer"
    # ACTRISEBASVAR = "concNno"
    # ACTRISEBASVAR = "concNno2"
    # ACTRISEBASVAR = "concNhno3"
    # ACTRISEBASVAR = "concNnh3"
    # ACTRISEBASVAR = "concnh4"
    # ACTRISEBASVAR = "concSso2"
    # ACTRISEBASVAR = "vmrco"
    # ACTRISEBASVAR = "concno3pm10"
    # ACTRISEBASVAR = "concno3pm25"
    # ACTRISEBASVAR = "concno3pm1"
    # ACTRISEBASVAR = "concnh4pm25"
    # ACTRISEBASVAR = "concnh4pm1"
    # ACTRISEBASVAR = "concso4c"
    # ACTRISEBASVAR = "concso4t"
    # ACTRISEBASVAR = "concso4pm25"
    # ACTRISEBASVAR = "concso4pm1"
    # ACTRISEBASVAR = "concCecpm25"
    # ACTRISEBASVAR = "concCecpm10"
    # ACTRISEBASVAR = "concCocpm25"
    # ACTRISEBASVAR = "concCocpm10"
    # ACTRISEBASVAR = "concom1"
    # ACTRISEBASVAR = "concsspm10"
    # ACTRISEBASVAR = "concsspm25"
    # ACTRISEBASVAR = "wetrdn"
    # ACTRISEBASVAR = "wetoxs"
    ACTRISEBASVAR = "wetoxn"
    # ACTRISEBASVAR = "prmm"
    # ACTRISEBASVAR = "vmro3"
    # ACTRISEBASVAR = "sc550aer"
    ACTRISEBASVARLIST = [
        "concNno",
        "concNno2",
        # "concNtno3",
        "concNhno3",
        # "concNtnh",
        "concNnh3",
        "concnh4",
        "concSso2",
        "concso4t",
        "concso4c",
        "vmro3",
        # "vmro3max",
        # "vmro3mda8",
        # "vmrox",
        "vmrco",
        "concpm10",
        "concpm25",
        "concno3pm10",
        "concno3pm25",
        "concno3pm1",
        "concnh4pm25",
        "concnh4pm1",
        "concso4pm25",
        "concso4pm1",
        "concCecpm10",
        "concCecpm25",
        "concCocpm10",
        "concCocpm25",
        "concom1",
        "concsspm10",
        "concsspm25",
        "wetrdn",
        "wetoxs",
        "wetoxn",
        "prmm",
    ]

    ACTRISEBASMANYVARLIST = (
        "concso4t",
        "concso4c",
    )

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

    def test_pyaerocom_actrisebas_all_vars(self):
        # test all vars one after another for reading via pyaerocom using a station filter
        # and a year filter to keep the data volume low
        for var in self.ACTRISEBASVARLIST:
            logger.info(f"Started testing reading of {var}")
            self.test_pyaerocom_actrisebas_single_var(var)
            logger.info(f"Finished testing reading of {var}")

    def test_pyaerocom_actrisebas_single_var(self, var_name=ACTRISEBASVAR):
        # test reading via pyaerocom
        try:
            from pyaerocom.io.pyaro.pyaro_config import PyaroConfig
            from pyaerocom.io import ReadUngridded
        except ImportError:
            assert "pyaerocom not installed"
            return

        data_name = "PYARO_actrisebas"
        data_id = "actrisebas"
        filter = {
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
                    var_name,
                ]
            },
            "time_bounds": {
                "startend_include": [("2019-01-01 00:00:00", "2020-12-31 00:00:00")]
            },
        }
        # needs to be the variable name for actrisebas
        url = var_name
        obsconfig = PyaroConfig(
            name=data_name,
            reader_id=data_id,
            filename_or_obj_or_url=url,
            filters=filter,
        )
        reader = ReadUngridded(f"{data_name}")
        data = reader.read(vars_to_retrieve=var_name, configs=obsconfig)
        if len(data.unique_station_names) < 2:
            logger.info(
                "less than 2 stations found. Removing station filter and trying again..."
            )
            filter = {
                "variables": {
                    "include": [
                        var_name,
                    ]
                },
                "time_bounds": {
                    "startend_include": [("2019-01-01 00:00:00", "2020-12-31 00:00:00")]
                },
            }
            obsconfig = PyaroConfig(
                name=data_name,
                reader_id=data_id,
                filename_or_obj_or_url=url,
                filters=filter,
            )
            reader = ReadUngridded(f"{data_name}")
            data = reader.read(vars_to_retrieve=var_name, configs=obsconfig)

        self.assertGreaterEqual(len(data.unique_station_names), 2)
        self.assertIn(url, data.contains_vars)
        logger.info(
            f"Found {len(data.unique_station_names)} stations for variable {var_name}"
        )

    def test_pyaerocom_actrisebas_single_var_all_stations(self):
        # test reading via pyaerocom
        try:
            from pyaerocom.io.pyaro.pyaro_config import PyaroConfig
            from pyaerocom.io import ReadUngridded
        except ImportError:
            assert "pyaerocom not installed"
            return

        data_name = "PYARO_actrisebas"
        data_id = "actrisebas"
        filter = {
            "variables": {
                "include": [
                    self.ACTRISEBASVAR,
                ]
            },
            "time_bounds": {
                "startend_include": [("2023-01-01 00:00:00", "2023-12-31 00:00:00")]
            },
        }
        # needs to be the variable name for actrisebas
        url = self.ACTRISEBASVAR
        obsconfig = PyaroConfig(
            name=data_name,
            reader_id=data_id,
            filename_or_obj_or_url=url,
            filters=filter,
        )
        reader = ReadUngridded(f"{data_name}")
        data = reader.read(vars_to_retrieve=self.ACTRISEBASVAR, configs=obsconfig)

        self.assertGreaterEqual(len(data.unique_station_names), 2)
        self.assertIn(url, data.contains_vars)
        logger.info(
            f"Found {len(data.unique_station_names)} stations for variable {self.ACTRISEBASVAR}"
        )

    def test_pyaerocom_actrisebas_many_var(self, var_list=ACTRISEBASMANYVARLIST):
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
            "variables": {"include": var_list},
        }
        # needs to be the variable name for actrisebas, but PyaroConfig wants this to a string and not a list
        # (the pydantic setup is too pedantic)
        url = ",".join(var_list)
        obsconfig = PyaroConfig(
            name=data_name,
            reader_id=data_id,
            filename_or_obj_or_url=url,
            filters=station_filter,
        )
        reader = ReadUngridded(f"{data_name}")
        data = reader.read(vars_to_retrieve=var_list, configs=obsconfig)
        self.assertGreaterEqual(len(data.unique_station_names), 4)
        self.assertIn("Ispra", data.unique_station_names)
        for _var in var_list:
            self.assertIn(_var, data.contains_vars)


if __name__ == "__main__":
    unittest.main()
