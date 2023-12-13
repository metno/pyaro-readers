# pyaro-readers
implementations of readers for the pyaerocom project using pyaro as interface

## Installation
`python -m pip install 'pyaro-readers@git+https://github.com/metno/pyaro-readers.git'`   

This will install pyaro and pyaro-readers and all their dependencies.

## Supported readers
* aeronetsunreader  
Reader for aeronet sun version 3 data.  
The reader supports reading from an uncompressed local file and from an URL providing a zip file or an
uncompressed file.  
If a zip file URL is provided, only the 1st file in there is used (since the 
Aeronet provided zip contains all data in a single file)

## Usage
### aeronetsunreader
```python
import pyaro.timeseries
TEST_URL = "https://pyaerocom.met.no/pyaro-suppl/testdata/aeronetsun_testdata.csv"
engine = pyaro.list_timeseries_engines()["aeronetsunreader"]
ts = engine.open(TEST_URL, filters=[], fill_country_flag=False)
print(ts.variables())
# stations
ts.data('AOD_550nm')['stations']
# start_times
ts.data('AOD_550nm')['start_times']
# stop_times
ts.data('AOD_550nm')['stop_times']
# latitudes
ts.data('AOD_550nm')['latitudes']
# longitudes
ts.data('AOD_550nm')['longitudes']
# altitudes
ts.data('AOD_550nm')['altitudes']
# values
ts.data('AOD_550nm')['values']

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