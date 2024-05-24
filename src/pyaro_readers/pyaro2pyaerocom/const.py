import logging

logger = logging.getLogger(__name__)

#: EBAS name
EBAS_MULTICOLUMN_NAME = "EBASMC"
# needed because we reused the ebas nasa ames reader from pyaerocom
EBAS_DB_LOCAL_CACHE = True

#: standard names for coordinates
STANDARD_COORD_NAMES = ["latitude", "longitude", "altitude"]
