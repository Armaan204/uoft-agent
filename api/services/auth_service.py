"""
api/services/auth_service.py - Google OAuth and JWT helpers.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests
from jose import JWTError, jwt

from auth.user_store import get_or_create_user

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_DAYS = 7


class AuthServiceError(RuntimeError):
    """Raised when OAuth or JWT operations fail."""


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise AuthServiceError(f"{name} must be configured")
    return value


def build_google_oauth_url(redirect_uri: str) -> str:
    params = {
        "client_id": _required_env("GOOGLE_CLIENT_ID"),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


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
    return payload


def get_or_create_backend_user(google_userinfo: dict[str, Any]) -> dict[str, Any]:
    google_id = str(google_userinfo.get("sub") or "").strip()
    email = google_userinfo.get("email")
    if not google_id:
        raise AuthServiceError("Google user info missing subject identifier")
    return get_or_create_user(google_id=google_id, email=email)


def create_access_token(user: dict[str, Any]) -> str:
    secret = _required_env("JWT_SECRET")
    expires_at = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS)
    payload = {
        "user_id": user.get("id"),
        "email": user.get("email"),
        "google_id": user.get("google_id"),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    secret = _required_env("JWT_SECRET")
    try:
        return jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise AuthServiceError("Invalid or expired token") from exc
