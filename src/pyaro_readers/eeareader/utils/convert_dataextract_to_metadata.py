"""
DataExtract.csv must be downloaded from https://discomap.eea.europa.eu/App/AQViewer/index.html?fqn=Airquality_Dissem.b2g.measurements
"""

import csv

metadata = []
with open("DataExtract.csv") as f:
    dataextract_full = csv.reader(f)
    for dataextract in dataextract_full:
        country = dataextract[0].strip()
        station_code = dataextract[6].strip()
        station_natcode = dataextract[7].strip()
        station_name = dataextract[8].strip()
        long = dataextract[11].strip()
        lat = dataextract[12].strip()
        alt = dataextract[13].strip()
        station_area = dataextract[15].strip()
        station_type = dataextract[16].strip()

        samplingpoint_id = dataextract[9]

        metadata.append(
            f"{samplingpoint_id}, {country}, {station_code}, {long}, {lat}, {alt}, {station_area}, {station_type}, \n"
        )

with open("../metadata.csv", "w") as f:
    for line in metadata:
        f.write(line)
