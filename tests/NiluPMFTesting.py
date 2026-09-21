import pyaro

TEST_URL = "testdata/PMF_EBAS/NO0042G.20171109070000.20220406124026.high_vol_sampler..pm10.4mo.1w.NO01L_hvs_week_no42_pm10.NO01L_NILU_sunset_002.lev2.nas"


def main():
    with pyaro.open_timeseries("nilupmfebas", TEST_URL, filters=[]) as ts:
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
