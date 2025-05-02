import os

import pyaro

EBAS_URL = file = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "testdata", "NILU"
)


def test_stuff():
    with pyaro.open_timeseries(
        "mergingreader",
        [
            {"reader_id": "ascii2netcdf", "filename_or_obj_or_url": EBAS_URL},
            {"reader_id": "ascii2netcdf", "filename_or_obj_or_url": EBAS_URL},
        ],
        mode="concat",
        filters=[],
    ) as ts:
        ts.variables()
        ts.stations()
        _data = ts.data("sulphur_dioxide_in_air")

        _metadata = ts.metadata()
