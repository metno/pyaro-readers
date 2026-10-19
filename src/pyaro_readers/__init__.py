from importlib import metadata

__version__ = metadata.version(__package__)

from .units_helpers import *

from .actrisebas.GetAerovalConfig import AerovalConfig
