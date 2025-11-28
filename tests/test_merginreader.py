import os

import pyaro
from pyaro_readers.merging_reader import MergingReader

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


def test_with_zero_len_dataset():
    d0 = {"reader_id": "ascii2netcdf", "filename_or_obj_or_url": EBAS_URL}
    d1 = {
        "reader_id": "ascii2netcdf",
        "filename_or_obj_or_url": EBAS_URL,
        "filters": {"stations": {"include": ["gibberish-non-existent-station"]}},
    }
    reader = MergingReader([d0, d1], mode="concat", filters=[])

    data = reader.data("sulphur_dioxide_in_air")
    _units = data.units
    _values = data.values
