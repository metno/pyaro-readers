"""
response.json can be downloaded with
curl -X 'GET'   'https://eeadmz1-downloads-api-appservice.azurewebsites.net/Property'   -H 'accept: text/plain' > response.json

concentration.csv can be found at https://dd.eionet.europa.eu/vocabulary/uom/concentration
"""

import json

pollutants = [
    "SO2",
    "PM10",
    "PM2.5",
    "O3",
    "NO2",
    "CO",
    "NO",
    "OC",
    "EC",
    "C6H6",
    "EC in PM2.5",
    "OC in PM2.5",
    "EC in PM10",
    "OC in PM10",
    "NH4+ in PM2.5",
    "NO3- in PM2.5",
    "NH4+ in PM10",
    "NO3- in PM10",
    "HNO3",
]

with open("response.json", "r") as f:
    properties = {}
    data = json.load(f)
    for entry in data:
        properties[entry["notation"]] = entry["id"].split("/")[-1]


with open("concentration.csv", encoding="utf-8-sig") as source:
    response = {}
    for line in source:
        words = line.split(",")
        # print(words)
        idd = words[0].split("/")[-1][:-1]
        unit = words[3]

        response[idd] = unit
        print(f'"{idd}" = {unit}')

with open("datatest.toml", "w") as target:
    target.write("[defaults]\n")
    target.write('"pollutatnts" = [\n')
    for poll in pollutants:
        target.write(f'"{poll}",\n')
    target.write("]\n\n")

    target.write("[units]\n")
    for key in response:
        target.write(f'"{key}" = {response[key]}\n')
    target.write("\n\n")
    target.write("[pollutant]\n")
    for entry in properties:
        target.write(f'{properties[entry]} = "{entry}" \n')
