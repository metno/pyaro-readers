"""Keycloak-authenticated xarray/OPeNDAP access against THREDDS.

Standalone adaptation of the auth pattern used in production by
ebas-portal-web (utils/keycloak_auth.py) + ebas-web-plotting (ebas_plot.py) —
same logic, no Flask session / plotting dependency.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests
import xarray as xr
import pydap


KEYCLOAK_TOKEN_URL = os.getenv(
    "KEYCLOAK_TOKEN_URL",
    "https://thredds.nilu.no/auth/realms/ebas/protocol/openid-connect/token",
)
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "ebas-cli")
KEYCLOAK_TIMEOUT_SECONDS = 10


class DatasetAccessError(Exception):
    """OPeNDAP data endpoint denied or failed access; carries the HTTP status that caused it."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class TokenState:
    access_token: str
    refresh_token: str
    expires_at: float


def _token_state_from_response(payload: dict) -> TokenState:
    return TokenState(
        access_token=payload["access_token"],
        refresh_token=payload["refresh_token"],
        expires_at=time.time() + payload["expires_in"],
    )


def login(username: str, password: str) -> TokenState:
    """Keycloak Resource-Owner-Password-Credentials grant."""
    response = requests.post(
        KEYCLOAK_TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": KEYCLOAK_CLIENT_ID,
            "username": username,
            "password": password,
        },
        timeout=KEYCLOAK_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _token_state_from_response(response.json())


def refresh(state: TokenState) -> TokenState:
    """Refresh-token grant — same client, no password re-entry."""
    response = requests.post(
        KEYCLOAK_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": KEYCLOAK_CLIENT_ID,
            "refresh_token": state.refresh_token,
        },
        timeout=KEYCLOAK_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _token_state_from_response(response.json())


def ensure_fresh(state: TokenState, margin_s: float = 30) -> TokenState:
    """Session-less equivalent of keycloak_auth.ensure_fresh_access_token():
    refresh only if the access token is within `margin_s` of expiring."""
    if time.time() <= state.expires_at - margin_s:
        return state
    return refresh(state)


def open_dataset(url: str, token: str | None = None) -> xr.Dataset:
    """Open an OPeNDAP dataset, authenticated if `token` is given.

    Adapted from ebas_plot.open_dataset(): probes the data endpoint first
    since netCDF4's own DAP client doesn't surface a 401/403 quickly (it
    silently retries for 40-120s before raising a generic error).
    """
    headers = {"Authorization": f"Bearer {token}"} if token else None
    try:
        probe = requests.get(f"{url}.dods?time[0:1:0]", headers=headers, timeout=5)
    except requests.exceptions.RequestException as exc:
        raise DatasetAccessError(503, f"OPeNDAP server unreachable: {exc}") from exc
    if probe.status_code in (401, 403):
        raise DatasetAccessError(probe.status_code, "Dataset is restricted")
    if probe.status_code >= 500:
        raise DatasetAccessError(503, f"OPeNDAP server error ({probe.status_code})")

    if token:
        # xarray's engine="pydap" shortcut doesn't expose a `protocol` kwarg
        # (it always leaves protocol=None, letting pydap probe/guess and warn),
        # so build the pydap dataset + store directly instead.
        from pydap.client import open_url

        # from xarray.backends.pydap_ import PydapDataStore
        from xarray.backends import PydapDataStore

        session = requests.Session()
        session.headers["Authorization"] = f"Bearer {token}"
        pydap_dataset = open_url(url, session=session, protocol="dap2")
        store = PydapDataStore(pydap_dataset, protocol="dap2")
        return xr.open_dataset(store)

    return xr.open_dataset(url, engine="netcdf4")
