import os
import unittest
import logging

import pyaro
import pyaro.timeseries

# from pyaro.timeseries.Wrappers import VariableNameChangingReader

logger = logging.getLogger(__name__)

TEST_URL = "https://prod-actris-md2.nilu.no/"


class TestActrisEbasTimeSeriesReader(unittest.TestCase):
    log_file = os.getenv("PYAEROCOM_LOG_FILE")
    if log_file is not None:
        log_file = f"actrisebas.log"
        # log_file = f"/home/jang/tmp/logging/pyaerocom.log"
    logging.basicConfig(filename=log_file, level=logging.DEBUG)
    logger.info("Started")

    engine = "actrisebas"
    # actris_vars_to_read = ["aerosol particle elemental carbon mass concentration"]
    # pyaerocom_vars_to_read = ["conco3"]
    # pyaerocom_vars_to_read = ["vmro3"]
    # pyaerocom_vars_to_read = ["wetso4"]
    # pyaerocom_vars_to_read = ["concca"]
    # pyaerocom_vars_to_read = ["concso2"]
    # pyaerocom_vars_to_read = ["vmrso2"]

    # pyaerocom_vars_to_read = ["concso4t"]
    pyaerocom_vars_to_read = ["concso4c"]
    # pyaerocom_vars_to_read = ["concpm10"]
    # pyaerocom_vars_to_read = ["concpm25"]
    # pyaerocom_vars_to_read = ["concpm1"]

    station_filter = pyaro.timeseries.Filter.StationFilter(
        ["Schmucke", "Birkenes II", "Jungfraujoch", "Ispra", "Melpitz", "Westerland"],
        [],
    )

    variable_filter_pyaerocom = pyaro.timeseries.Filter.VariableNameFilter(
        {}, pyaerocom_vars_to_read, []
    )
    # variable_filter_actris = pyaro.timeseries.Filter.VariableNameFilter(
    #     {}, actris_vars_to_read, []
    # )

    # "start_include": [("2019-01-01 00:00:00", "2023-12-24 00:00:00")]

    # filters on "start_include"
    # time_filter = pyaro.timeseries.Filter.TimeBoundsFilter([("2019-01-01 00:00:00", "2019-12-31 23:59:59")])
    time_filter = pyaro.timeseries.Filter.TimeBoundsFilter(
        [("2019-01-01 00:00:00", "2020-12-31 23:59:59")]
    )

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

    # ACTRIS vocabulary usage has been postponed for the moment
    # def test_api_reading_small_data_set(self):
    #     filters = [self.station_filter, self.variable_filter_actris, self.time_filter]
    #     engine = pyaro.list_timeseries_engines()[self.engine]
    #     with engine.open(
    #         TEST_URL,
    #         filters=filters,
    #     ) as ts:
    #         self.assertGreaterEqual(len(ts.variables()), 1)
    #         self.assertGreaterEqual(len(ts.stations()), 1)
    #         self.assertGreaterEqual(len(ts._data[ts.variables()[0]]), 100)
    #         self.assertGreaterEqual(len(ts.data(ts.variables()[0])), 100)
    #         self.assertGreaterEqual(len(ts.variables()), 1)
    #         self.assertIn("revision", ts.metadata())

    def test_api_reading_pyaerocom_naming(self):
        # test access to the EBAS API
        # test variable by variable
        for _var in self.pyaerocom_vars_to_read:
            variable_filter_pyaerocom = pyaro.timeseries.Filter.VariableNameFilter(
                {}, [_var], []
            )
            filters = [self.station_filter, variable_filter_pyaerocom, self.time_filter]
            engine = pyaro.list_timeseries_engines()[self.engine]
            with engine.open(TEST_URL, filters=filters) as ts:
                self.assertGreaterEqual(len(ts.variables()), 1)
                self.assertGreaterEqual(len(ts.stations()), 1)
                self.assertIn("Schmucke", ts.stations())
                self.assertGreaterEqual(len(ts._data[ts.variables()[0]]), 1000)
                self.assertGreaterEqual(len(ts.data(ts.variables()[0])), 1000)
                self.assertIn("revision", ts.metadata())

    # ACTRIS vocabulary usage has been postponed for the moment
    # def test_wrappers(self):
    #     engine = pyaro.list_timeseries_engines()[self.engine]
    #     new_var_name = "vmro3"
    #     ebas_var_name = "ozone mass concentration"
    #     filters = [self.station_filter, self.variable_filter_actris]
    #
    #     with VariableNameChangingReader(
    #         engine.open(
    #             TEST_URL,
    #             filters=filters,
    #         ),
    #         reader_to_new={ebas_var_name: new_var_name},
    #     ) as ts:
    #         self.assertEqual(ts.data(new_var_name).variable, new_var_name)
    #         self.assertGreaterEqual(len(ts.variables()), 1)
    #         self.assertGreaterEqual(len(ts.stations()), 2)
    #         self.assertGreaterEqual(len(ts.data(ts.variables()[0])), 1000)
    #         self.assertIn("revision", ts.metadata())


if __name__ == "__main__":
    unittest.main()
