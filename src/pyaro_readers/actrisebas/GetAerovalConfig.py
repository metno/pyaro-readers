import abc
import logging
from copy import deepcopy


class AerovalConfig(abc.ABC):
    """Small helper class to get a working Aeroval configuration"""

    def __init__(self):
        pass

    DEFAULT_WEB_NAME = "ACTRIS-EBAS-d"
    DEFAULT_TS_TYPE = "daily"
    DEFAULT_VERT_TYPE = "Surface"
    DEFAULT_CONF_BASE_NAME = "ACTRIS-EBAS-d-tc"
    DEFAULT_OBS_ID_BASE_NAME = "ACTRIS-EBAS-d"
    DEFAULT_READER_ID = "actrisebas"
    DEFAULT_TIME_FILTER = {
        "time_bounds": {
            "startend_include": [("1990-01-01 00:00:00", "2030-01-01 00:00:00")]
        }
    }

    @staticmethod
    def get_actris_ebas_config(
        vars: list,
        web_name: str = DEFAULT_WEB_NAME,
        ts_type: str = DEFAULT_TS_TYPE,
        obs_vert_type: str = DEFAULT_VERT_TYPE,
        conf_base_name: str = DEFAULT_CONF_BASE_NAME,
        obs_id_base_name: str = DEFAULT_OBS_ID_BASE_NAME,
        time_filter: dict = DEFAULT_TIME_FILTER,
    ) -> dict:
        """create ACTRIS-EBAS configuration from list of variables"""
        obs_config_dict = {}
        for _idx, _var in enumerate(vars):
            _obs_dict = {}
            conf_name = f"{conf_base_name}-{_var}"
            pyaro_name = f"{obs_id_base_name}-{_idx}"
            var_filter = {"variables": {"include": [_var]}}
            # time_filter = {'time_bounds': {'startend_include': [('2023-01-01 00:00:00', '2024-01-01 00:00:00')]}}
            pyaro_config_dict = dict(
                name=conf_name,
                reader_id=AerovalConfig.DEFAULT_READER_ID,
                filename_or_obj_or_url="",
                filters={**var_filter, **time_filter},
            )

            _obs_dict = dict(
                obs_id=conf_name,
                obs_name=pyaro_name,
                web_interface_name=web_name,
                pyaro_config=pyaro_config_dict,
                obs_vert_type=obs_vert_type,
                ts_type=ts_type,
                obs_vars=[_var],
            )
            obs_config_dict[conf_name] = deepcopy(_obs_dict)

        return obs_config_dict

    @staticmethod
    def get_time_filter_str(start_year: int, end_year: int) -> dict:
        """small helper method to create the dictionary for a time filer"""
        time_str = {
            "time_bounds": {
                "startend_include": [
                    (f"{start_year}-01-01 00:00:00", f"{end_year}-12-31 23:59:59")
                ]
            }
        }
        return time_str
