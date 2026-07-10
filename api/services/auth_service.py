"""
api/services/auth_service.py - Google OAuth, Supabase password auth, and JWT helpers.
"""

from __future__ import annotations

import logging
import os
import secrets
import uuid

logger = logging.getLogger(__name__)
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests
import jwt
from jwt.exceptions import PyJWTError as JWTError
from supabase import create_client

from api.auth.user_store import (
    _load_user_by,
    get_or_create_google_user,
    get_or_create_password_user,
)

get_or_create_user = get_or_create_google_user

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRY_MINUTES = 15
REFRESH_TOKEN_EXPIRY_DAYS = 7
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


class AuthServiceError(RuntimeError):
    """Raised when OAuth, password auth, or JWT operations fail."""


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise AuthServiceError(f"{name} must be configured")
    return value


def _normalize_email(email: str | None) -> str:
    normalized = (email or "").strip().lower()
    if not normalized or "@" not in normalized:
        raise AuthServiceError("A valid email address is required")
    return normalized


def _validate_password(password: str | None) -> str:
    value = password or ""
    if len(value) < MIN_PASSWORD_LENGTH:
        raise AuthServiceError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(value) > MAX_PASSWORD_LENGTH:
        raise AuthServiceError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters")
    if not any(ch.isalpha() for ch in value) or not any(ch.isdigit() for ch in value):
        raise AuthServiceError("Password must include at least one letter and one number")
    return value


def _frontend_url(path: str) -> str:
    base = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    return f"{base}{path}"


def _supabase_auth_client():
    url = _required_env("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
    if not key:
        raise AuthServiceError("SUPABASE_ANON_KEY or SUPABASE_KEY must be configured")
    return create_client(url, key)


def _supabase_user_value(user: Any, field: str) -> Any:
    if user is None:
        return None
    if isinstance(user, dict):
        return user.get(field)
    return getattr(user, field, None)


def _supabase_user_confirmed(user: Any) -> bool:
    return bool(
        _supabase_user_value(user, "email_confirmed_at")
        or _supabase_user_value(user, "confirmed_at")
    )


def build_google_oauth_url(redirect_uri: str) -> tuple[str, str]:
    """Return (oauth_url, state) with a cryptographic CSRF state token."""
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": _required_env("GOOGLE_CLIENT_ID"),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}", state


def exchange_google_code(code: str, redirect_uri: str) -> dict[str, Any]:
    data = {
        "code": code,
        "client_id": _required_env("GOOGLE_CLIENT_ID"),
        "client_secret": _required_env("GOOGLE_CLIENT_SECRET"),
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    token_response = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=30)
    if not token_response.ok:
        raise AuthServiceError(
            f"Google token exchange failed: {token_response.status_code} {token_response.text}"
        )

    access_token = token_response.json().get("access_token")
    if not access_token:
        raise AuthServiceError("Google token exchange returned no access_token")

    userinfo_response = requests.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if not userinfo_response.ok:
        raise AuthServiceError(
            f"Google user info lookup failed: {userinfo_response.status_code} {userinfo_response.text}"
        )

    payload = userinfo_response.json()
    google_id = payload.get("sub")
    if not google_id:
        raise AuthServiceError("Google user info returned no subject identifier")
    if not payload.get("email"):
        raise AuthServiceError("Google user info returned no email address")
    return payload


def get_or_create_backend_user(google_userinfo: dict[str, Any]) -> dict[str, Any]:
    google_id = str(google_userinfo.get("sub") or "").strip()
    email = google_userinfo.get("email")
    if not google_id:
        raise AuthServiceError("Google user info missing subject identifier")
    user = get_or_create_user(google_id=google_id, email=email)
    user["name"] = google_userinfo.get("name")
    user["auth_provider"] = "google"
    return user


def signup_with_password(email: str, password: str) -> None:
    clean_email = _normalize_email(email)
    clean_password = _validate_password(password)
    existing = _load_user_by("email", clean_email)
    if existing and existing.get("google_id"):
        raise AuthServiceError("An account with this email already exists. Try signing in with Google.")
    try:
        response = _supabase_auth_client().auth.sign_up({
            "email": clean_email,
            "password": clean_password,
            "options": {"email_redirect_to": _frontend_url("/signin?confirmed=true")},
        })
    except Exception as exc:
        logger.error("Supabase signup error: %s", exc)
        raise AuthServiceError("Unable to create account") from exc

    user = getattr(response, "user", None)
    identities = _supabase_user_value(user, "identities")
    if isinstance(identities, list) and len(identities) == 0:
        raise AuthServiceError("An account with this email already exists")


def login_with_password(email: str, password: str) -> dict[str, Any]:
    clean_email = _normalize_email(email)
    if not password:
        raise AuthServiceError("Invalid email or password")
    try:
        response = _supabase_auth_client().auth.sign_in_with_password({
            "email": clean_email,
            "password": password,
        })
    except Exception as exc:
        raise AuthServiceError("Invalid email or password") from exc

    auth_user = getattr(response, "user", None)
    logger.info(
        "Supabase login user: email_confirmed_at=%s confirmed_at=%s type=%s",
        _supabase_user_value(auth_user, "email_confirmed_at"),
        _supabase_user_value(auth_user, "confirmed_at"),
        type(auth_user).__name__,
    )
    auth_user_id = _supabase_user_value(auth_user, "id")
    auth_email = _supabase_user_value(auth_user, "email") or clean_email
    if not auth_user_id:
        raise AuthServiceError("Invalid email or password")
    if not _supabase_user_confirmed(auth_user):
        raise AuthServiceError("Please verify your email before signing in")

    user = get_or_create_password_user(auth_user_id=str(auth_user_id), email=str(auth_email))
    user["auth_user_id"] = str(auth_user_id)
    user["auth_provider"] = "password"
    return user


def send_password_reset(email: str) -> None:
    clean_email = _normalize_email(email)
    existing = _load_user_by("email", clean_email)
    if existing and existing.get("google_id") and not existing.get("auth_user_id"):
        return
    try:
        _supabase_auth_client().auth.reset_password_for_email(
            clean_email,
            {"redirect_to": _frontend_url("/auth/reset-password")},
        )
    except Exception as exc:
        raise AuthServiceError("Unable to send password reset email") from exc


def reset_password(access_token: str, refresh_token: str, new_password: str) -> None:
    if not access_token or not refresh_token:
        raise AuthServiceError("Invalid or expired password reset link")
    clean_password = _validate_password(new_password)
    client = _supabase_auth_client()
    try:
        client.auth.set_session(access_token, refresh_token)
        client.auth.update_user({"password": clean_password})
    except Exception as exc:
        msg = str(exc).lower()
        if "same_password" in msg or "different" in msg:
            raise AuthServiceError("New password must be different from your current password") from exc
        raise AuthServiceError("Unable to reset password") from exc


def create_access_token(user: dict[str, Any]) -> str:
    secret = _required_env("JWT_SECRET")
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=ACCESS_TOKEN_EXPIRY_MINUTES)
    payload = {
        "user_id": user.get("id"),
        "email": user.get("email"),
        "name": user.get("name"),
        "google_id": user.get("google_id"),
        "auth_user_id": user.get("auth_user_id"),
        "auth_provider": user.get("auth_provider") or ("google" if user.get("google_id") else "password"),
        "type": "access",
        "exp": int(expires_at.timestamp()),
        "iat": int(now.timestamp()),
        "iss": "uoft-agent",
        "aud": "uoft-agent",
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def create_refresh_token(user: dict[str, Any]) -> str:
    secret = _required_env("JWT_SECRET")
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=REFRESH_TOKEN_EXPIRY_DAYS)
    payload = {
        "user_id": user.get("id"),
        "type": "refresh",
        "exp": int(expires_at.timestamp()),
        "iat": int(now.timestamp()),
        "iss": "uoft-agent",
        "aud": "uoft-agent",
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    secret = _required_env("JWT_SECRET")
    try:
        payload = jwt.decode(
            token, secret, algorithms=[JWT_ALGORITHM],
            audience="uoft-agent", issuer="uoft-agent",
        )
    except (jwt.exceptions.InvalidAudienceError,
            jwt.exceptions.InvalidIssuerError,
            jwt.exceptions.MissingRequiredClaimError):
        try:
            payload = jwt.decode(
                token, secret, algorithms=[JWT_ALGORITHM],
                options={"verify_aud": False, "verify_iss": False},
            )
        except JWTError as exc:
            raise AuthServiceError("Invalid or expired token") from exc
    except JWTError as exc:
        raise AuthServiceError("Invalid or expired token") from exc
    if payload.get("type") == "refresh":
        raise AuthServiceError("Refresh token cannot be used as access token")
    return payload


def decode_refresh_token(token: str) -> dict[str, Any]:
    secret = _required_env("JWT_SECRET")
    try:
        payload = jwt.decode(
            token, secret, algorithms=[JWT_ALGORITHM],
            audience="uoft-agent", issuer="uoft-agent",
        )
    except JWTError as exc:
        raise AuthServiceError("Invalid or expired refresh token") from exc
    if payload.get("type") != "refresh":
        raise AuthServiceError("Invalid refresh token type")
    return payload


def refresh_access_token(refresh_token_str: str) -> tuple[str, dict[str, Any]]:
    """Validate a refresh token and return a fresh (access_token, user_dict)."""
    payload = decode_refresh_token(refresh_token_str)
    user_id = payload.get("user_id")
    if not user_id:
        raise AuthServiceError("Invalid refresh token")
    user = _load_user_by("id", user_id)
    if not user:
        raise AuthServiceError("User not found")
    return create_access_token(user), user


def delete_user_account(user_id: str) -> None:
    """Cascade-delete all data for one user across all Supabase tables."""
    from api.auth.user_store import get_supabase_client
    client = get_supabase_client()
    tables_with_user_id = [
        "chat_messages",
        "chat_conversations",
        "grades_snapshot",
        "grade_overrides",
        "grades_cache",
        "acorn_imports",
        "manual_deadlines",
        "manual_courses",
        "quercus_tokens",
        "syllabus_weights_cache",
        "program_requirements_cache",
    ]
    for table in tables_with_user_id:
        try:
            client.table(table).delete().eq("user_id", user_id).execute()
        except Exception:
            logger.warning("Failed to delete from %s for user_id=%s", table, user_id)
    try:
        client.table("users").delete().eq("id", user_id).execute()
    except Exception as exc:
        raise AuthServiceError("Failed to delete user account") from exc
