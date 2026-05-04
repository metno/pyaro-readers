from __future__ import annotations

import os
import sys


if sys.version_info >= (3, 11):  # pragma: no cover
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

_META_KEYS = "meta_keys.toml"

_META_KEYS_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), _META_KEYS)


def ghost_meta_keys() -> list[str]:
    with open(_META_KEYS_path, "rb") as f:
        variables = tomllib.load(f)
    return variables["ghost_meta_keys"]
