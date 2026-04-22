"""
api/services/acorn_service.py - ACORN import storage logic for FastAPI routes.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

from auth.user_store import get_supabase_client
from integrations.acorn_store import AcornStoreError, validate_payload

load_dotenv()


class AcornServiceError(RuntimeError):
    """Raised when the ACORN storage layer is misconfigured or fails."""


def _get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise AcornServiceError("SUPABASE_URL and SUPABASE_KEY must be configured")
    return create_client(url, key)


def import_acorn_data(import_code: str, data: dict[str, Any]) -> dict:
    """Validate and persist one ACORN import payload to Supabase."""
    payload = dict(data or {})
    payload["importCode"] = import_code
    validated = validate_payload(payload)
    row = {
        "import_code": validated["importCode"],
        "user_id": None,
        "data": validated,
        "imported_at": validated["importedAt"],
    }
    try:
        response = _get_supabase().table("acorn_imports").insert(row).execute()
    except Exception as exc:
        raise AcornServiceError("Failed to store ACORN import") from exc

    rows = getattr(response, "data", None) or []
    if not rows:
        raise AcornServiceError("Supabase returned no inserted ACORN import row")
    return validated


def get_latest_import(import_code: str) -> dict | None:
    """Return the latest ACORN import payload for one import code, or None."""
    normalized = validate_payload({"importCode": import_code, "courses": []})["importCode"]
    try:
        response = (
            _get_supabase()
            .table("acorn_imports")
            .select("data")
            .eq("import_code", normalized)
            .order("imported_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise AcornServiceError("Failed to load latest ACORN import") from exc

    rows = getattr(response, "data", None) or []
    if not rows:
        return None
    return rows[0].get("data")


def get_import_status(import_code: str) -> dict:
    """Return whether imported ACORN data exists for one import code."""
    normalized = validate_payload({"importCode": import_code, "courses": []})["importCode"]
    try:
        response = (
            _get_supabase()
            .table("acorn_imports")
            .select("data")
            .eq("import_code", normalized)
            .order("imported_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise AcornServiceError("Failed to load ACORN import status") from exc

    rows = getattr(response, "data", None) or []
    if not rows:
        return {"exists": False, "importedAt": None, "importCode": normalized}

    latest = rows[0].get("data") or {}
    return {
        "exists": True,
        "importedAt": latest.get("importedAt"),
        "importCode": latest.get("importCode", normalized),
        "courseCount": len(latest.get("courses", [])),
    }


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
        raise AcornServiceError("Failed to load saved ACORN import") from exc

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

    normalized = validate_payload({"importCode": import_code, "courses": []})["importCode"]
    client = get_supabase_client()

    try:
        lookup = (
            client
            .table("acorn_imports")
            .select("id, data, imported_at")
            .eq("import_code", normalized)
            .order("imported_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise AcornServiceError("Failed to load ACORN import to claim") from exc

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
        raise AcornServiceError("Failed to claim ACORN import for user") from exc

    data = dict(row.get("data") or {})
    if row.get("imported_at") and not data.get("importedAt"):
        data["importedAt"] = row["imported_at"]
    return data
