import logging
import os
import unittest

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
    # ACTRISEBASVAR = "concNtnh"
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
    # ACTRISEBASVAR = "wetoxn"
    # ACTRISEBASVAR = "prmm"
    ACTRISEBASVAR = "vmro3"
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

    EEA_VAR = "vmro3"
    # EEA_VAR = "vmrno2"

    AIRNOW_VAR = "vmro3"

    EEA_PATH = (
        "/lustre/storeB/project/aerocom/aerocom1/AEROCOM_OBSDATA/EEA-AQDS/download"
    )
    EEA_CATALOG_FILE_VERIFIED = os.path.join(EEA_PATH, "verified", "catalog.parquet")
    EEA_CATALOG_FILE_UNVERIFIED = os.path.join(
        EEA_PATH, "unverified", "catalog.parquet"
    )

    ################
    #    EEA-rural parquet
    ################
    EEA_CONFIG = (
        dict(
            obs_id="EEA-d-rural",
            obs_vars=[
                # "concpm10",
                # "concpm25",
                # "vmrno2",
                "vmro3",
                #            "concSso2",
                #            "concNno2",
                #            "concNno",
                #            "vmro3max",
            ],
            pyaro_config={
                "name": "EEA-d-rural",
                "reader_id": "mergingreader",
                "filename_or_obj_or_url": [
                    {
                        "reader_id": "eeareader",
                        "filename_or_obj_or_url": EEA_CATALOG_FILE_VERIFIED,
                        # "dataset": "verified",
                        "station_area": [
                            "rural",
                            "rural-regional",
                            "rural-nearcity",
                            "rural-remote",
                        ],
                        "station_type": [
                            "background",
                        ],
                    },
                    {
                        "reader_id": "eeareader",
                        "filename_or_obj_or_url": EEA_CATALOG_FILE_UNVERIFIED,
                        # "dataset": "unverified",
                        "station_area": [
                            "rural",
                            "rural-regional",
                            "rural-nearcity",
                            "rural-remote",
                        ],
                        "station_type": [
                            "background",
                        ],
                    },
                ],
                "mode": "concat",
                "name_map": {
                    "PM2.5": "concpm25",
                    "PM10": "concpm10",
                    "NO": "concno",
                    "NO2": "concno2",
                    "SO2": "concso2",
                    "O3": "conco3",
                },
                "filters": {
                    "time_bounds": {
                        "startend_include": [
                            #                        (f"{year}-01-01 00:00:00", f"{year+1}-01-01 00:00:00")
                            (f"2019-01-01 00:00:00", f"2019-12-31 23:59:59")
                        ],
                    },
                    "valleyfloor_relaltitude": {
                        "topo": "/lustre/storeB/project/aerocom/aerocom1/AEROCOM_OBSDATA/GTOPO30/merged",
                        "radius": 5000,
                        "topo_var": "Band1",
                        "lower": None,
                        "upper": 500,
                    },
                },
                "post_processing": [
                    "vmro3_from_conco3",
                    "vmrno2_from_concno2",
                    #                "concNno_from_concno",
                    #                "concNno2_from_concno2",
                    #                "concSso2_from_concso2",
                    #                "vmro3max_from_conco3",
                ],
            },
            web_interface_name="EEA-d-rural",
            obs_vert_type="Surface",
            #        obs_filters={**ALTITUDE_FILTER},
            ts_type="daily",
        ),
    )

    GHOSTVAR = "concso4"

    def test_pyaerocom_ghost_single_var(self):
        # test the ghost reader via pyaerocom
        try:
            from pyaerocom.io.pyaro.pyaro_config import PyaroConfig
            from pyaerocom.io import ReadUngridded
        except ImportError:
            assert "pyaerocom not installed"
            return

        data_name = "ghosttest"
        data_id = "ghostreader"
        url = (
            "/lustre/storeB/project/aerocom/aerocom1/AEROCOM_OBSDATA/GHOST_v2/download"
        )
        obsconfig = PyaroConfig(
            name=data_name,
            reader_id=data_id,
            filename_or_obj_or_url=url,
            filters={
                "time_bounds": {
                    "startend_include": [("2019-01-01 00:00:00", "2020-01-01 00:00:00")]
                },  # Include data between these time bounds
                "variables": {"include": ["sconcso4"]},
            },
            networks=[
                "EEA",
                "US_EPA_AQS",
            ],
            area_classifications=[
                "rural",
                "rural-near_city",
                "rural-regional",
                "rural-remote",
            ],
            station_classifications=["background"],
            frequency="monthly",
            compressed=True,
            # name_map={self.GHOSTVAR: "sconcso4"},
            name_map={"sconcso4": self.GHOSTVAR},
        )
        reader = ReadUngridded(f"{data_name}")
        data = reader.read(vars_to_retrieve=["sconcso4", "concso4"], configs=obsconfig)
        # data = reader.read(configs=obsconfig)
        self.assertGreaterEqual(len(data.unique_station_names), 4)
        self.assertIn("Alta_Floresta", data.unique_station_names)

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

    def test_pyaerocom_eea_single_var(self, var_name=EEA_VAR):
        # test reading via pyaerocom
        try:
            from pyaerocom.io.pyaro.pyaro_config import PyaroConfig
            from pyaerocom.io import ReadUngridded
        except ImportError:
            assert "pyaerocom not installed"
            return

        data_name = f"PYARO_eea_rural"
        data_id = "eeareader"
        filter = {
            "time_bounds": {
                "startend_include": [("2010-01-01 00:00:00", "2019-12-31 23:59:59")]
            },
            "countries": {"include": ["NO", "LU"]},
        }
        # needs to be the variable name for actrisebas
        url = self.EEA_CATALOG_FILE_VERIFIED
        obsconfig = PyaroConfig(
            name=data_name,
            reader_id=data_id,
            filename_or_obj_or_url=url,
            filters=filter,
            name_map={
                "O3": "conco3",
                # "NO2": "concno2",
            },
            post_processing=[
                "vmro3_from_conco3",
                # "vmrno2_from_concno2",
            ],
            # special for the eeareader
            station_area=[
                "rural",
                "rural-regional",
                "rural-nearcity",
                "rural-remote",
            ],
            station_type=[
                "background",
            ],
        )
        reader = ReadUngridded(f"{data_name}")
        data = reader.read(vars_to_retrieve=var_name, configs=obsconfig)

        self.assertGreaterEqual(len(data.unique_station_names), 2)
        self.assertIn(var_name, data.contains_vars)
        logger.info(
            f"Found {len(data.unique_station_names)} stations for variable {var_name}"
        )
        if len(data.unique_station_names) > 10:
            logger.info(f"1st 10 stations: {','.join(data.unique_station_names[:10])}")
        else:
            logger.info(f"Stations: {','.join(data.unique_station_names)}")

    def test_pyaerocom_twmoe_single_var(self, var_name=EEA_VAR):
        # test reading via pyaerocom
        try:
            from pyaerocom.io.pyaro.pyaro_config import PyaroConfig
            from pyaerocom.io import ReadUngridded
        except ImportError:
            assert "pyaerocom not installed"
            return

        # twmoe_config = PyaroConfig(
        # name="TWMOE",
        # reader_id="harp",
        # filename_or_obj_or_url="/lustre/storeB/project/aerocom/aerocom1/AEROCOM_OBSDATA/TWMOE/aggregated/",
        # filters={"variables": {
        #     "include": ["PM10_density", "PM2p5_density", "O3_volume_mixing_ratio", "NO2_volume_mixing_ratio"]}},
        # name_map={"PM10_density": "concpm10", "PM2p5_density": "concpm25", "O3_volume_mixing_ratio": "vmro3",
        #           "NO2_volume_mixing_ratio": "vmrno2", "CH4_volume_mixing_ratio": "vmrch4",
        #           "CO_volume_mixing_ratio": "vmrco", "SO2_volume_mixing_ratio": "vmrso2"},
        # )

        data_name = f"PYARO_TWMOE"
        data_id = "harp"
        filter = {
            # "time_bounds": {
            #     "startend_include": [("2010-01-01 00:00:00", "2019-12-31 23:59:59")]
            # },
            "variables": {
                "include": [
                    "O3_volume_mixing_ratio",
                ]
            },
            # "include": ["PM10_density", "PM2p5_density", "O3_volume_mixing_ratio", "NO2_volume_mixing_ratio"]},
        }
        url = (
            "/lustre/storeB/project/aerocom/aerocom1/AEROCOM_OBSDATA/TWMOE/aggregated/"
        )
        obsconfig = PyaroConfig(
            name=data_name,
            reader_id=data_id,
            filename_or_obj_or_url=url,
            filters=filter,
            name_map={
                "O3_volume_mixing_ratio": "vmro3",
            },
            # name_map={"PM10_density": "concpm10", "PM2p5_density": "concpm25", "O3_volume_mixing_ratio": "vmro3",
            #       "NO2_volume_mixing_ratio": "vmrno2", "CH4_volume_mixing_ratio": "vmrch4",
            #       "CO_volume_mixing_ratio": "vmrco", "SO2_volume_mixing_ratio": "vmrso2"},
        )
        reader = ReadUngridded(f"{data_name}")
        data = reader.read(vars_to_retrieve=var_name, configs=obsconfig)

        self.assertGreaterEqual(len(data.unique_station_names), 2)
        self.assertIn(var_name, data.contains_vars)
        logger.info(
            f"Found {len(data.unique_station_names)} stations for variable {var_name}"
        )
        if len(data.unique_station_names) > 10:
            logger.info(f"1st 10 stations: {','.join(data.unique_station_names[:10])}")
        else:
            logger.info(f"Stations: {','.join(data.unique_station_names)}")


if __name__ == "__main__":
    unittest.main()
