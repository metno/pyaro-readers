from io import BytesIO

import numpy as np
import polars
import pandas

from pyaro_readers.parquet import ParquetTimeseriesReader


def test_reading():
    N = 1000

    times = pandas.date_range("2025-02-28 00:00", freq="1h", periods=N + 1)

    ds_tmp = polars.DataFrame(
        {
            "variable": "vespene",
            "units": "kg/m^3",
            "value": np.random.random(N),
            "station": "base",
            "longitude": 10,
            "latitude": 59,
            "start_time": times[:-1],
            "end_time": times[1:],
        }
    )
    tmpfile = BytesIO()
    ds_tmp.write_parquet(tmpfile)
    tmpfile.seek(0)

    ds = ParquetTimeseriesReader(tmpfile, filters=[])

    stations = ds.stations()
    assert len(stations) == 1
    station = stations["base"]
    assert station.longitude == 10
    assert station.latitude == 59
    assert station.long_name == "base"

    assert np.unique(ds.variables()) == ["vespene"]

    data = ds.data("vespene")

    assert np.all(data.start_times == times[:-1])
    assert np.all(data.end_times == times[1:])
    assert np.all(ds_tmp["value"].to_numpy() == data.values)

    data_slice = data[:500]
    assert len(data_slice) == 500
    assert np.all(ds_tmp["value"][:500].to_numpy() == data_slice.values)
    assert data.units == "kg/m^3"


def test_read_with_metadata():
    N = 1000

    times = pandas.date_range("2025-02-28 00:00", freq="1h", periods=N + 1)

    ds_tmp = polars.DataFrame(
        {
            "variable": "vespene",
            "units": "kg/m^3",
            "value": np.random.random(N),
            "station": "base",
            "longitude": 10,
            "latitude": 59,
            "start_time": times[:-1],
            "end_time": times[1:],
            "station_type": "urban",
        }
    )
    tmpfile = BytesIO()
    ds_tmp.write_parquet(tmpfile)
    tmpfile.seek(0)

    ds = ParquetTimeseriesReader(
        tmpfile, station_metadata_fields=["station_type"], filters=[]
    )

    stations = ds.stations()
    assert len(stations) == 1
    station = stations["base"]
    assert station.longitude == 10
    assert station.latitude == 59
    assert station.long_name == "base"
    assert station.metadata["station_type"] == "urban"
