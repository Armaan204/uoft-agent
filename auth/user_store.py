"""
auth/user_store.py — Supabase-backed user and Quercus token persistence.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from supabase import Client, create_client

from integrations.encryption import decrypt_token, encrypt_token

load_dotenv()

try:
    import streamlit as st
    from streamlit.errors import StreamlitSecretNotFoundError
except Exception:  # pragma: no cover - streamlit import is expected in app usage
    st = None

    class StreamlitSecretNotFoundError(Exception):
        pass


class UserStoreError(RuntimeError):
    """Raised when the Supabase-backed user store is misconfigured or fails."""


def _secret_or_env(name: str) -> str | None:
    if st is not None:
        try:
            value = st.secrets.get(name)
        except StreamlitSecretNotFoundError:
            value = None
        if value:
            return value
    return os.getenv(name)


def get_supabase_client() -> Client:
    """Return a Supabase client using app secrets or environment variables."""
    url = _secret_or_env("SUPABASE_URL")
    key = _secret_or_env("SUPABASE_KEY")
    if not url or not key:
        raise UserStoreError("SUPABASE_URL and SUPABASE_KEY must be configured")
    return create_client(url, key)


def get_or_create_user(google_id: str, email: str | None) -> dict:
    """Upsert the current Streamlit-auth user and return the stored row."""
    if not google_id or not str(google_id).strip():
        raise UserStoreError("google_id must be a non-empty string")

    payload = {
        "google_id": str(google_id).strip(),
        "email": (email or "").strip() or None,
    }
    try:
        response = (
            get_supabase_client()
            .table("users")
            .upsert(payload, on_conflict="google_id")
            .execute()
        )
    except Exception as exc:
        raise UserStoreError("Failed to upsert user") from exc

    rows = getattr(response, "data", None) or []
    if rows:
        return rows[0]

    try:
        lookup = (
            get_supabase_client()
            .table("users")
            .select("*")
            .eq("google_id", payload["google_id"])
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise UserStoreError("Failed to load user after upsert") from exc

    rows = getattr(lookup, "data", None) or []
    if not rows:
        raise UserStoreError("Supabase returned no user row after upsert")
    return rows[0]


def save_quercus_token(user_id: str | int, token: str) -> None:
    """Encrypt and upsert one persisted Quercus token per user."""
    if user_id is None or user_id == "":
        raise UserStoreError("user_id must be provided")
    encrypted = encrypt_token(token)
    try:
        client = get_supabase_client()
        existing = (
            client
            .table("quercus_tokens")
            .select("id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise UserStoreError(f"Failed to check existing Quercus token: {exc}") from exc

    rows = getattr(existing, "data", None) or []
    try:
        if rows:
            (
                client
                .table("quercus_tokens")
                .update({"token": encrypted})
                .eq("id", rows[0]["id"])
                .execute()
            )
        else:
            (
                client
                .table("quercus_tokens")
                .insert({
                    "user_id": user_id,
                    "token": encrypted,
                })
                .execute()
            )
    except Exception as exc:
        raise UserStoreError(f"Failed to save Quercus token: {exc}") from exc


def get_quercus_token(user_id: str | int) -> str | None:
    """Load and decrypt the persisted Quercus token for one user."""
    if user_id is None or user_id == "":
        return None

    try:
        response = (
            get_supabase_client()
            .table("quercus_tokens")
            .select("token")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise UserStoreError("Failed to load Quercus token") from exc

    rows = getattr(response, "data", None) or []
    if not rows:
        return None

    encrypted = rows[0].get("token")
    if not encrypted:
        return None
    try:
        return decrypt_token(encrypted)
    except Exception as exc:
        raise UserStoreError("Failed to decrypt Quercus token") from exc


def delete_quercus_token(user_id: str | int) -> None:
    """Delete the persisted Quercus token for one user."""
    if user_id is None or user_id == "":
        return
    try:
        (
            get_supabase_client()
            .table("quercus_tokens")
            .delete()
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        raise UserStoreError("Failed to delete Quercus token") from exc
