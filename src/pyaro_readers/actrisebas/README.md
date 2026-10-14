# additional documantation for the actris EBAS reader
This document contains some more detailed information about the actris EBAS reader.

## Things to remember
- although the URLs given by the API are DOIs, the data might not be invariable over time. That is 
because the DOI
is valid for the underlaying data in the EBAS database, but not the actual export to netcdf files. 
The cached netcdf files are therfore only valid for a default time of 24h, with the possibility to
extend that time via the environment variable `PYARO_ACTRIS_EBAS_CACHE_TIME`. The time has to be
given in seconds.
- This reader has an independant caching capability, that is only activated if the user sets the environment
variable `PYARO_CACHE_DIR_EBAS_ACTRIS`. The directory needs to exist.

## Basic algorithm
1. look in the [toml file](definitions.toml) for the requested variable name
2. find the corresponding actris_variable in the field `actris_variable`
3. Query the api; cache complete API response for 24h.
3. check API response for time coverage
4. if the covered time is in the requested time range, pre-fill a lookup table
connecting the OpenDAP URL with the data variable in the netcdf file using the 
combination of `actris_variable`, `ebas_matrix` and
the `units` field from the toml file and the data given in the API response`
5. open data file (either using the OpenDAP protocol or by using the cached file); cache
new files on disc (complete file) for 24h.

