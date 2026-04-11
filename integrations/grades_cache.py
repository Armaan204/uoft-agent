"""
integrations/grades_cache.py — persisted grade snapshots and manual overrides.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

try:
    import streamlit as st
    from streamlit.errors import StreamlitSecretNotFoundError
except Exception:  # pragma: no cover - streamlit import is expected in app usage
    st = None

    class StreamlitSecretNotFoundError(Exception):
        pass


class GradesCacheError(RuntimeError):
    """Raised when grade snapshot persistence fails."""


def _secret_or_env(name: str) -> str | None:
    if st is not None:
        try:
            value = st.secrets.get(name)
        except StreamlitSecretNotFoundError:
            value = None
        if value:
            return value
    return os.getenv(name)


def _get_supabase_client() -> Client:
    url = _secret_or_env("SUPABASE_URL")
    key = _secret_or_env("SUPABASE_KEY")
    if not url or not key:
        raise GradesCacheError("SUPABASE_URL and SUPABASE_KEY must be configured")
    return create_client(url, key)


def _to_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _normalise_component(component: dict) -> dict:
    key = str(component.get("component_key") or "").strip()
    name = str(component.get("name") or "").strip()
    if not key:
        raise GradesCacheError("Each component must include a non-empty component_key")
    if not name:
        raise GradesCacheError("Each component must include a non-empty name")
    return {
        "component_key": key,
        "component_name": name,
        "score": _to_float(component.get("earned")),
        "possible": _to_float(component.get("possible")),
    }


def get_saved_grades(user_id: str | int, course_id: int | str) -> dict[str, dict]:
    """Return the last acknowledged live snapshot keyed by component_key."""
    if not user_id:
        return {}

    try:
        response = (
            _get_supabase_client()
            .table("grades_cache")
            .select("component_key, component_name, score, possible, acknowledged_at, saved_at")
            .eq("user_id", user_id)
            .eq("course_id", int(course_id))
            .execute()
        )
    except Exception as exc:
        raise GradesCacheError(f"Failed to load saved grades: {exc}") from exc

    rows = getattr(response, "data", None) or []
    return {
        row["component_key"]: {
            "component_name": row.get("component_name"),
            "score": _to_float(row.get("score")),
            "possible": _to_float(row.get("possible")),
            "acknowledged_at": row.get("acknowledged_at"),
            "saved_at": row.get("saved_at"),
        }
        for row in rows
        if row.get("component_key")
    }


def get_grade_overrides(user_id: str | int, course_id: int | str) -> dict[str, dict]:
    """Return manual overrides keyed by component_key."""
    if not user_id:
        return {}

    try:
        response = (
            _get_supabase_client()
            .table("grade_overrides")
            .select("component_key, manual_score, manual_possible, created_at")
            .eq("user_id", user_id)
            .eq("course_id", int(course_id))
            .execute()
        )
    except Exception as exc:
        raise GradesCacheError(f"Failed to load grade overrides: {exc}") from exc

    rows = getattr(response, "data", None) or []
    return {
        row["component_key"]: {
            "manual_score": _to_float(row.get("manual_score")),
            "manual_possible": _to_float(row.get("manual_possible")),
            "created_at": row.get("created_at"),
        }
        for row in rows
        if row.get("component_key")
    }


def detect_new_grades(user_id: str | int, course_id: int | str, live_components: list[dict]) -> list[str]:
    """Return component keys whose live grade differs from the saved snapshot."""
    saved = get_saved_grades(user_id, course_id)
    changed = []

    for component in live_components:
        if component.get("status") != "graded":
            continue
        current = _normalise_component(component)
        cached = saved.get(current["component_key"])
        if cached is None:
            changed.append(current["component_key"])
            continue

        if (
            cached.get("score") != current["score"]
            or cached.get("possible") != current["possible"]
            or cached.get("component_name") != current["component_name"]
        ):
            changed.append(current["component_key"])

    return changed


def save_grades(user_id: str | int, course_id: int | str, components: list[dict]) -> None:
    """Upsert the current live graded component snapshot and acknowledge it."""
    if not user_id:
        raise GradesCacheError("user_id must be provided")

    graded_components = [
        _normalise_component(component)
        for component in components
        if component.get("status") == "graded"
    ]
    if not graded_components:
        return

    acknowledged_at = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "user_id": user_id,
            "course_id": int(course_id),
            "component_key": component["component_key"],
            "component_name": component["component_name"],
            "score": component["score"],
            "possible": component["possible"],
            "acknowledged_at": acknowledged_at,
            "saved_at": acknowledged_at,
        }
        for component in graded_components
    ]

    try:
        (
            _get_supabase_client()
            .table("grades_cache")
            .upsert(rows, on_conflict="user_id,course_id,component_key")
            .execute()
        )
    except Exception as exc:
        raise GradesCacheError(f"Failed to save grades: {exc}") from exc


def save_grade_override(
    user_id: str | int,
    course_id: int | str,
    component_key: str,
    manual_score: float,
    manual_possible: float,
) -> None:
    """Upsert one manual grade override."""
    if not user_id:
        raise GradesCacheError("user_id must be provided")
    if not component_key:
        raise GradesCacheError("component_key must be provided")

    row = {
        "user_id": user_id,
        "course_id": int(course_id),
        "component_key": str(component_key),
        "manual_score": float(manual_score),
        "manual_possible": float(manual_possible),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        (
            _get_supabase_client()
            .table("grade_overrides")
            .upsert(row, on_conflict="user_id,course_id,component_key")
            .execute()
        )
    except Exception as exc:
        raise GradesCacheError(f"Failed to save grade override: {exc}") from exc
