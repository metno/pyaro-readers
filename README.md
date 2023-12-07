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
