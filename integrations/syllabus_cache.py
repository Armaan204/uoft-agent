"""
integrations/syllabus_cache.py — persistent storage for parsed syllabus weights.
"""

from __future__ import annotations

import os

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


class SyllabusCacheError(RuntimeError):
    """Raised when the persistent syllabus cache is misconfigured or fails."""


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
        raise SyllabusCacheError("SUPABASE_URL and SUPABASE_KEY must be configured")
    return create_client(url, key)


def get_cached_syllabus_weights(course_id: int | str, source_ref: str) -> dict[str, float] | None:
    """Return cached parsed syllabus weights for one course/source pair."""
    try:
        response = (
            _get_supabase_client()
            .table("syllabus_weights_cache")
            .select("weights")
            .eq("course_id", int(course_id))
            .eq("source_ref", source_ref)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise SyllabusCacheError(f"Failed to load cached syllabus weights: {exc}") from exc

    rows = getattr(response, "data", None) or []
    if not rows:
        return None
    weights = rows[0].get("weights")
    return weights if isinstance(weights, dict) else None


def save_cached_syllabus_weights(course_id: int | str, source_ref: str, weights: dict[str, float]) -> None:
    """Persist parsed syllabus weights for one course/source pair."""
    payload = {
        "course_id": int(course_id),
        "source_ref": source_ref,
        "weights": weights,
    }

    try:
        client = _get_supabase_client()
        existing = (
            client
            .table("syllabus_weights_cache")
            .select("id")
            .eq("course_id", int(course_id))
            .eq("source_ref", source_ref)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise SyllabusCacheError(f"Failed to check cached syllabus weights: {exc}") from exc

    rows = getattr(existing, "data", None) or []
    try:
        if rows:
            (
                client
                .table("syllabus_weights_cache")
                .update({"weights": weights})
                .eq("id", rows[0]["id"])
                .execute()
            )
        else:
            (
                client
                .table("syllabus_weights_cache")
                .insert(payload)
                .execute()
            )
    except Exception as exc:
        raise SyllabusCacheError(f"Failed to save cached syllabus weights: {exc}") from exc
