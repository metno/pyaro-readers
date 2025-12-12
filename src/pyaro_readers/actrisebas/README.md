# additional documantation for the actris EBAS reader
This documen contains some more detailed information about the actris EBAS reader.

## Basic algorithm
1. look in the [toml file](definitions.toml) for the requested variable name
2. search API for the corresponding actris_variable
3. check API response for time coverage
4. if the covered time is in the requested time range, open data file using the OpenDAP protocol
5. search for data variables using the standard_names  from the toml file

