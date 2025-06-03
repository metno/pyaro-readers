# pyaro-readers
implementations of readers for the pyaerocom project using pyaro as interface

## Installation
`python -m pip install pyaro-readers`

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

### nilupmfebas: EBAS format (Nasa-Ames)
Reader for random EBAS data in NASA-AMES format. This reader is tested only with PMF data provided by
NILU, but should in principle able to read any random text file in EBAS NASA-AMES.
The variables provided contain in EBAS terms a combination of matrix, component and unit with a number sign (#)
as seperator (e.g. `pm10_pm25#total_carbon#ug C m-3"` or `pm10#organic_carbon##ug C m-3` or `pm10#galactosan#ng m-3`)

### EEA: Parquet format
Reader for the EEA files provided by https://eeadmz1-downloads-webapp.azurewebsites.net/. The reader reads the **hourly only** data of the unverified dataset. The directory structure must be
```
metadata.csv
unverified
    - NO
    - SE
        - SPO-SE395030_00038_100.parquet
        - ...
    - ...
```
where `metadata.csv` is csv file containing station metadata (https://discomap.eea.europa.eu/App/AQViewer/index.html?fqn=Airquality_Dissem.b2g.measurements).

### ACTRIS-EBAS (alpha version)
Reader for the EBAS data of the ACTRIS data portal (https://data.actris.eu/).
This reader talks directly to the API at [https://prod-actris-md2.nilu.no/](https://prod-actris-md2.nilu.no/). 

Because the variable naming supported at this early stage uses the naming scheme of the 
[pyaerocom project](https://pyaerocom.readthedocs.io/en/latest/), this reader is depending on pyaerocom being installed
and supports only a very limited number of variables.
Additional variables can be added editing the file [`definitions.toml`](src/pyaro_readers/actrisebas/definitions.toml).
The ACTRIS vocabulary is [here](https://vocabulary.actris.nilu.no/skosmos/actris_vocab/en/).

## Usage
### aeronetsunreader
```python
import pyaro
TEST_URL = "https://pyaerocom.met.no/pyaro-suppl/testdata/aeronetsun_testdata.csv"
with pyaro.open_timeseries("aeronetsunreader", TEST_URL, filters=[], fill_country_flag=False) as ts:
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


### nilupmfebas
```python
import pyaro
TEST_URL = "testdata/PMF_EBAS/NO0042G.20171109070000.20220406124026.high_vol_sampler..pm10.4mo.1w.NO01L_hvs_week_no42_pm10.NO01L_NILU_sunset_002.lev2.nas"
def main():
    with pyaro.open_timeseries(
        'nilupmfebas', TEST_URL, filters=[]
    ) as ts:
        variables = ts.variables()
        for var in variables:
            data = ts.data(var)
            print(f"var:{var} ; unit:{data.units}")
            # stations
            print(set(data.stations))
            # start_times
            print(data.start_times)
            for idx, time in enumerate(data.start_times):
                print(f"{time}: {data.values[idx]}")
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

if __name__ == "__main__":
    main()
```


### eeareader
```python
import pyaro
import pyaro.timeseries

TEST_URL = "/lustre/storeB/project/aerocom/aerocom1/AEROCOM_OBSDATA/EEA-AQDS/download"


def main():
    with pyaro.open_timeseries(
        "eeareader",
        TEST_URL,
        filters=[
            pyaro.timeseries.Filter.CountryFilter(include=["NO", "SE", "DK"]),
            pyaro.timeseries.Filter.TimeBoundsFilter(
                startend_include=[("2023-01-01 00:00:00", "2024-01-01 00:00:00")]
            ),
        ],
        enable_progressbar=True,
    ) as ts:
        # help(ts)
        data = ts.data("PM10")
        print(data.values)


if __name__ == "__main__":
    main()
```

### ACTRIS-EBAS
```python
import pyaro
import pyaro.timeseries

TEST_URL = "" #unused but needs to be passed at this stage

def main():
    read_engine = "actrisebas"
    pyaerocom_vars_to_read = ["vmro3"]

    station_filter = pyaro.timeseries.Filter.StationFilter(
    ["Schmucke", "Birkenes II", "Jungfraujoch", "Ispra", "Melpitz", "Westerland"], []
    )

    time_filter = pyaro.timeseries.Filter.TimeBoundsFilter([("2019-01-01 00:00:00", "2020-12-31 23:59:59")])
    for _var in pyaerocom_vars_to_read:
            variable_filter_pyaerocom = pyaro.timeseries.Filter.VariableNameFilter(include=[_var])
            filters = [station_filter, variable_filter_pyaerocom, time_filter]
            engine = pyaro.list_timeseries_engines()[read_engine]
            with engine.open(TEST_URL, filters=filters) as ts:
                print(ts.data[_var])

if __name__ == "__main__":
    main()
```

### mergingreader

This reader can merge data from different pyaro readers.

```python
import pyaro
import pyaro.timeseries

TEST_URL = "/lustre/storeB/project/aerocom/aerocom1/AEROCOM_OBSDATA/EEA-AQDS/download"


def main():
    with pyaro.open_timeseries(
        "mergingreader",
        [{
            "reader_id": "eeareader",
            "filename_or_obj_or_url": TEST_URL,
            "dataset": "verified",
        },
        {
            "reader_id": "eeareader",
            "filename_or_obj_or_url": TEST_URL,
            "dataset": "unverified",
        }],
        mode="concat",
        filters=[
            pyaro.timeseries.Filter.CountryFilter(include=["NO", "SE", "DK"]),
        ],
    ) as ts:
        # help(ts)
        data = ts.data("PM10")
        print(data.values)


if __name__ == "__main__":
    main()
```

### lcsreader
```python
import pyaro

TEST_URL = "/lustre/storeB/project/aerocom/aerocom1/AEROCOM_OBSDATA/LCS/parquet/2022"


def main():
    with pyaro.open_timeseries(
        "lcsreader",
        TEST_URL,
        filters={},
        min_quality = 2,
        min_spread = 3,
    ) as ts:
        # help(ts)
        data = ts.data("PM25")
        print(data.values)


if __name__ == "__main__":
    main()
```