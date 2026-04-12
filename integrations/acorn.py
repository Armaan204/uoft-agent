"""
integrations/acorn.py — ACORN import helpers for UofT Agent.

ACORN has no public API. Instead of scraping credentials server-side,
the project expects a browser extension to read the user's already-
logged-in ACORN academic-history page and POST the parsed payload to the
backend API. Streamlit then claims the imported row to the logged-in
account and reads future visits back directly from Supabase by user ID.
"""

import os

import requests

from auth.user_store import get_supabase_client

ACORN_BACKEND_URL = os.getenv("ACORN_BACKEND_URL", "https://uoft-agent-production.up.railway.app").rstrip("/")


class AcornBackendError(Exception):
    """Raised when the ACORN backend cannot be reached or returns invalid data."""


class AcornStoreError(RuntimeError):
    """Raised when the Supabase-backed ACORN store cannot be queried or updated."""


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


def get_latest_import_for_user(user_id: str | int) -> dict | None:
    """Return the latest claimed ACORN import row for one user."""
    if user_id in (None, ""):
        return None

    try:
        response = (
            get_supabase_client()
            .table("acorn_imports")
            .select("id, data, imported_at")
            .eq("user_id", user_id)
            .order("imported_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise AcornStoreError("Failed to load saved ACORN import") from exc

    rows = getattr(response, "data", None) or []
    if not rows:
        return None

    row = rows[0]
    data = dict(row.get("data") or {})
    if row.get("imported_at") and not data.get("importedAt"):
        data["importedAt"] = row["imported_at"]
    return data


def claim_latest_import_for_user(import_code: str, user_id: str | int) -> dict | None:
    """Attach the newest import for one import code to the given user account."""
    if not import_code or not str(import_code).strip():
        raise AcornStoreError("import_code must be provided")
    if user_id in (None, ""):
        raise AcornStoreError("user_id must be provided")

    code = str(import_code).strip()
    client = get_supabase_client()

    try:
        lookup = (
            client
            .table("acorn_imports")
            .select("id, data, imported_at")
            .eq("import_code", code)
            .order("imported_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise AcornStoreError("Failed to load ACORN import to claim") from exc

    rows = getattr(lookup, "data", None) or []
    if not rows:
        return None

    row = rows[0]
    try:
        (
            client
            .table("acorn_imports")
            .update({"user_id": user_id})
            .eq("id", row["id"])
            .execute()
        )
    except Exception as exc:
        raise AcornStoreError("Failed to claim ACORN import for user") from exc

    data = dict(row.get("data") or {})
    if row.get("imported_at") and not data.get("importedAt"):
        data["importedAt"] = row["imported_at"]
    return data
