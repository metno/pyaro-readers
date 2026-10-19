import pandas as pd


class UnitConversionError(ValueError):
    pass


#: default frequency for rates variables (e.g. deposition, precip)
RATES_FREQ_DEFAULT = "d"

# 1. DEFINITION OF ATOM and MOLECULAR MASSES

# Atoms
M_O = 15.999  # u
M_S = 32.065  # u
M_N = 14.0067  # u
M_H = 1.00784  # u

# Molecules
M_SO2 = M_S + 2 * M_O
M_SO4 = M_S + 4 * M_O

M_NO2 = M_N + 2 * M_O
M_NO3 = M_N + 3 * M_O

M_NH3 = M_N + 3 * M_H
M_NH4 = M_N + 4 * M_H

# Unit conversion and custom units definitions

# 2.1 Other conversion factors
HA_TO_SQM = 10000  # hectar to square metre.

# 3. LOOKUP TABLE FOR CONVERSION FACTORS

#: Custom unit conversion factors for certain variables
#: columns: variable -> from unit -> to_unit -> conversion
#: factor
UCONV_MUL_FACS = pd.DataFrame(
    [
        # ["dryso4", "mg/m2/d", "mgS m-2 d-1", M_S / M_SO4],
        # ["drynh4", "mg/m2/d", "mgN m-2 d-1", M_N/ M_NH4],
        # ["concso4", "ug S/m3", "ug m-3", M_SO4 / M_S],
        # ["SO4ugSm3", "ug/m3", "ug S m-3", M_S / M_SO4],
        # ["concso4pm25", "ug S/m3", "ug m-3", M_SO4 / M_S],
        # ["concso4pm10", "ug S/m3", "ug m-3", M_SO4 / M_S],
        ["concso2", "ug S/m3", "ug m-3", M_SO2 / M_S],
        ["concbc", "ug C/m3", "ug m-3", 1.0],
        ["concoa", "ug C/m3", "ug m-3", 1.0],
        ["concoc", "ug C/m3", "ug m-3", 1.0],
        ["conctc", "ug C/m3", "ug m-3", 1.0],
        # a little hacky for ratpm10pm25...
        # ["ratpm10pm25", "ug m-3", "1", 1.0],
        ["concpm25", "ug m-3", "1", 1.0],
        ["concpm10", "ug m-3", "1", 1.0],
        ["concno2", "ug N/m3", "ug m-3", M_NO2 / M_N],
        # ["concno3", "ug N/m3", "ug m-3", M_NO3 / M_N],
        ["concnh3", "ug N/m3", "ug m-3", M_NH3 / M_N],
        # ["concnh4", "ug N/m3", "ug m-3", M_NH4 / M_N],
        ["wetso4", "kg S/ha", "kg m-2", M_SO4 / M_S / HA_TO_SQM],
        ["concso4pr", "mg S/L", "g m-3", M_SO4 / M_S],
    ],
    columns=["var_name", "from", "to", "fac"],
).set_index(["var_name", "from"])

# may be used to specify alternative names for custom units  defined
# in UCONV_MUL_FACS

UALIASES = {
    # mass concentrations
    # "ug S m-3": "ug S/m3",
    # "ug C m-3": "ug C/m3",
    # "ug N m-3": "ug N/m3",
    "ugC/m3": "ug C m-3",
    "ug C/m3": "ug C m-3",
    "ug/m3": "ug m-3",
    # deposition rates (implicit)
    ## sulphur species
    "mgS/m2": "mg S m-2",
    "mgSm-2": "mg S m-2",
    ## nitrogen species
    "mgN/m2": "mg N m-2",
    "mgNm-2": "mg N m-2",
    # deposition rates (explicit)
    ## sulphur species
    "mgS/m2/h": "mg S m-2 h-1",
    "mg/m2/h": "mg m-2 h-1",
    "mgS/m**2/h": "mg S m-2 h-1",
    "mgSm-2h-1": "mg S m-2 h-1",
    "mgSm**-2h-1": "mg S m-2 h-1",
    "mgS/m2/d": "mg S m-2 d-1",
    ## nitrogen species
    "mgN/m2/h": "mg N m-2 h-1",
    "mgN/m**2/h": "mg N m-2 h-1",
    "mgNm-2h-1": "mg N m-2 h-1",
    "mgNm**-2h-1": "mg N m-2 h-1",
    "mgN/m2/d": "mg N m-2 d-1",
    ## others
    "MM/H": "mm h-1",
    # others
    "/m": "m-1",
    "ng/m3": "ng m-3",
    "ug /m3": "ug m-3",
}
