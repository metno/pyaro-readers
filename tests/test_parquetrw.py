import os
import tempfile
import shutil

from pyaro_readers.parquetrw import ParquetRWReader


EBAS_URL = file = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "testdata", "NILU"
)


def test_parquet_rw_reader():
    cache_dir = tempfile.mkdtemp()

    reader = ParquetRWReader(
        {
            "reader_id": "ascii2netcdf",
            "filename_or_obj_or_url": EBAS_URL,
            "filters": [],
        },
        cache_dir=cache_dir,
        filters=[],
    )

    _vars = reader.variables()
    _vars = reader.variables()
    _stations = reader.stations()
    _stations = reader.stations()

    _data = reader.data("sulphur_dioxide_in_air")
    _data = reader.data("sulphur_dioxide_in_air")

    reader.close()

    reader = ParquetRWReader(
        {
            "reader_id": "ascii2netcdf",
            "filename_or_obj_or_url": EBAS_URL,
            "filters": [],
        },
        cache_dir=cache_dir,
        filters=[],
    )

    _vars = reader.variables()
    _stations = reader.stations()
    _data = reader.data("sulphur_dioxide_in_air")

    shutil.rmtree(cache_dir)
