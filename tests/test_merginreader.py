import os

import pyaro

EBAS_URL = file = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "testdata", "NILU"
)


def test_stuff():
    with pyaro.open_timeseries(
        "mergingreader",
        datasets=[
            {"readername": "ascii2netcdf", "filename": EBAS_URL},
            {"readername": "ascii2netcdf", "filename": EBAS_URL},
        ],
        mode="concat",
        filters=[],
    ) as ts:
        ts.variables()
        ts.stations()
        _data = ts.data("sulphur_dioxide_in_air")
