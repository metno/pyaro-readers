import os
import unittest

import pyaro
from pyaro_readers.merging_reader import MergingReader

EBAS_URL = file = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "testdata", "NILU"
)


class TestMergingReader(unittest.TestCase):
    def test_stuff(self):
        with pyaro.open_timeseries(
            "mergingreader",
            [
                {
                    "reader_id": "ascii2netcdf",
                    "filename_or_obj_or_url": EBAS_URL,
                    "filters": {"stations": {"include": ["NO0002", "NO0056"]}},
                },
                {
                    "reader_id": "ascii2netcdf",
                    "filename_or_obj_or_url": EBAS_URL,
                    "filters": {"stations": {"include": ["SE0005", "SE0014"]}},
                },
                {
                    "reader_id": "ascii2netcdf",
                    "filename_or_obj_or_url": EBAS_URL,
                    "filters": {"stations": {"include": ["NO9999"]}}, # non existent station
                },
            ],
            mode="concat",
            filters=[],
        ) as ts:
            ts.variables()
            stations = ts.stations()
            _data = ts.data("sulphur_dioxide_in_air")

            station_ids = _data.station_ids
            station_names = _data.stations
            self.assertEqual(len(station_ids), len(station_names))

            station_names2 = _data.stations_by_ids(station_ids)
            self.assertEqual(len(station_ids), len(station_names2))
            self.assertTrue(all(station_names == station_names2))

            station_names3 = _data.stations_by_ids([3, 3, 1, 2, 0])
            self.assertTrue(all(station_names3 == ["SE0014", "SE0014", "NO0056", "SE0005", "NO0002"]))

            _metadata = ts.metadata()


    def test_with_zero_len_dataset(self):
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
