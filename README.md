# pyaro-readers
implementations of readers for the pyaerocom project using pyaro as interface

## Installation
`python -m pip install 'pyaro-readers@git+https://github.com/metno/pyaro-readers.git'`

This will install pyaro and pyaro-readers and all their dependencies.

## Supported readers
### aeronetsunreader
Reader for aeronet sun version 3 data (https://aeronet.gsfc.nasa.gov/new_web/download_all_v3_aod.html).
The reader supports reading from an uncompressed local file and from an URL providing a zip file or an
uncompressed file.
If a zip file URL is provided, only the 1st file in there is used (since the
Aeronet provided zip contains all data in a single file).

### aeronetsdareader
Reader for aeronet SDA version 3 data (https://aeronet.gsfc.nasa.gov/new_web/download_all_v3_aod.html).
The reader supports reading from an uncompressed local file and from an URL providing a zip file, an
uncompressed file or a tar file (including all common compression formats).
If a zip file URL is provided, only the 1st file in there is used (since the
Aeronet provided zip contains all data in a single file).

### ascii2netcdf
Reader for databases created with MSC-W tools niluNasaAmes2Netcdf or eea_airquip2emepdata.py.
The database consists of a directory with a list of stations, i.e. `StationList.csv` and netcdf
data-files per year with resolutions `hourly`, `daily`, `weekly`, `monthly` and `yearly` and a naming
of `data_{resolution}.{YYYY}.nc`, e.g. `data_daily.2021.nc`. A test-database with daily data only
can be found under `tests/testdata/NILU`.

The MSC-W database contains the EBAS database for 1990-2021 and the EEA_Airquip database for
2016-2018 as of yearly 2024. The data in the database is already aggregated, i.e. daily files
contain already hourly data if enough hours have been measured. Therefore, `resolution` is a
required parameter.

### harp
Reader for NetCDF files that follow the [HARP](http://stcorp.github.io/harp/doc/html/conventions/)
conventions.


## Usage
### aeronetsunreader
```python
import pyaro
TEST_URL = "https://pyaerocom.met.no/pyaro-suppl/testdata/aeronetsun_testdata.csv"
with pyro.open_timeseries("aeronetsunreader", TEST_URL, filters=[], fill_country_flag=False) as ts:
    print(ts.variables())
    data = ts.data('AOD_550nm')
    # stations
    data.stations
    # start_times
    data.start_times
    # stop_times
    data.end_times
    # latitudes
    data.latitudes
    # longitudes
    data.longitudes
    # altitudes
    data.altitudes
    # values
    data.values

```
### aeronetsdareader
```python
import pyaro
TEST_URL = "https://pyaerocom.met.no/pyaro-suppl/testdata/SDA_Level20_Daily_V3_testdata.tar.gz"
with pyaro.open_timeseries("aeronetsdareader", TEST_URL, filters=[], fill_country_flag=False) as ts:
    print(ts.variables())
    data = ts.data('AODGT1_550nm')
    # stations
    data.stations
    # start_times
    data.start_times
    # stop_times
    data.end_times
    # latitudes
    data.latitudes
    # longitudes
    data.longitudes
    # altitudes
    data.altitudes
    # values
    data.values
```

### ascii2netcdf
```python
import pyaro
TEST_URL = "/lustre/storeB/project/fou/kl/emep/Auxiliary/NILU/"
with pyaro.open_timeseries(
    'ascii2netcdf', TEST_URL, resolution="daily", filters=[]
) as ts:
    data = ts.data("sulphur_dioxide_in_air")
    data.units # ug
    # stations
    data.stations
    # start_times
    data.start_times
    # stop_times
    data.end_times
    # latitudes
    data.latitudes
    # longitudes
    data.longitudes
    # altitudes
    data.altitudes
    # values
    data.values
```

### harpreader
```python
import pyaro

TEST_URL = "/lustre/storeB/project/aerocom/aerocom1/AEROCOM_OBSDATA/CNEMC/aggregated/sinca-surface-157-999999-001.nc"
with pyaro.open_timeseries(
    'harp', TEST_URL
) as ts:
    data = ts.data("CO_volume_mixing_ratio")
    data.units # ppm
    # stations
    data.stations
    # start_times
    data.start_times
    # stop_times
    data.end_times
    # latitudes
    data.latitudes
    # longitudes
    data.longitudes
    # altitudes
    data.altitudes
    # values
    data.values

```

### geocoder_reverse_natural_earth
geocoder_reverse_natural_earth is small helper to identify country codes for obs networks that don't mention the
countrycode of a station in their location data
```python
from geocoder_reverse_natural_earth import (
    Geocoder_Reverse_NE,
    Geocoder_Reverse_Exception,
)
geo = Geocoder_Reverse_NE()
print(geo.lookup(60, 10)["ISO_A2_EH"])
lat = 78.2361926
lon = 15.3692614
try:
    geo.lookup(lat, lon)
except Geocoder_Reverse_Exception as grex:
    dummy = geo.lookup_nearest(lat, lon)
    if dummy is None:
        print(f"error: {lat},{lon}")
    else:
        print(dummy["ISO_A2_EH"])



```
