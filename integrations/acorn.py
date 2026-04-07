"""
integrations/acorn.py — ACORN import helpers for UofT Agent.

ACORN has no public API. Instead of scraping credentials server-side,
the project now expects a browser extension to read the user's already-
logged-in ACORN academic-history page and POST the parsed payload to the
backend API. Streamlit reads the same payload back over HTTP using the
per-user import code.
"""

import os

import requests

ACORN_BACKEND_URL = os.getenv("ACORN_BACKEND_URL", "https://uoft-agent-production.up.railway.app").rstrip("/")


class AcornBackendError(Exception):
    """Raised when the ACORN backend cannot be reached or returns invalid data."""


def get_latest_import(import_code: str) -> dict | None:
    """Return the latest imported ACORN payload for one import code."""
    response = requests.get(
        f"{ACORN_BACKEND_URL}/api/acorn/latest",
        params={"import_code": import_code},
        timeout=15,
    )
    if not response.ok:
        raise AcornBackendError(f"ACORN latest request failed ({response.status_code}): {response.text}")

    payload = response.json()
    if not payload.get("ok"):
        raise AcornBackendError(payload.get("error", "ACORN latest request failed"))
    if not payload.get("exists"):
        return None
    return payload.get("data")


def get_import_status(import_code: str) -> dict:
    """Return whether ACORN data exists and when it was last imported."""
    response = requests.get(
        f"{ACORN_BACKEND_URL}/api/acorn/status",
        params={"import_code": import_code},
        timeout=15,
    )
    if not response.ok:
        raise AcornBackendError(f"ACORN status request failed ({response.status_code}): {response.text}")

    payload = response.json()
    if not payload.get("ok"):
        raise AcornBackendError(payload.get("error", "ACORN status request failed"))
    return payload
