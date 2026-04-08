"""
auth/google_auth.py — Google OAuth helpers for Streamlit.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import traceback

try:
    import streamlit as st
except Exception:
    print("Failed to import streamlit in auth.google_auth", flush=True)
    traceback.print_exc()
    raise

try:
    from googleapiclient.discovery import build
except Exception:
    print("Failed to import googleapiclient.discovery in auth.google_auth", flush=True)
    traceback.print_exc()
    raise

try:
    from google_auth_oauthlib.flow import Flow
except Exception:
    print("Failed to import google_auth_oauthlib.flow in auth.google_auth", flush=True)
    traceback.print_exc()
    raise

try:
    from streamlit.errors import StreamlitSecretNotFoundError
except Exception:
    print("Failed to import StreamlitSecretNotFoundError in auth.google_auth", flush=True)
    traceback.print_exc()
    raise

_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
]
_AUTH_URL_KEY = "_google_auth_url"


def init_google_auth() -> None:
    """Initialise the Google OAuth flow and process any callback."""
    st.session_state.pop("_google_auth_error", None)

    if st.session_state.get("google_user"):
        return

    code = st.query_params.get("code")
    if code:
        try:
            params_snapshot = {k: st.query_params.get_all(k) for k in st.query_params}
        except Exception:
            params_snapshot = {"error": "Could not read query params"}
        print(f"Google OAuth callback query params: {params_snapshot}", flush=True)
        state = st.query_params.get("state")
        try:
            _handle_callback(str(code), str(state) if state else None)
        except Exception:
            print("Google OAuth callback handling failed", flush=True)
            traceback.print_exc()
            raise
        return

    _, client_secret = _get_google_credentials()
    flow = _build_flow()
    print(f"Google OAuth Flow redirect_uri: {flow.redirect_uri}", flush=True)
    signed_state = _build_signed_state(client_secret)
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account",
        state=signed_state,
    )
    print(f"Google OAuth authorization URL: {authorization_url}", flush=True)
    st.session_state[_AUTH_URL_KEY] = authorization_url


def get_logged_in_user() -> dict | None:
    """Return the logged-in Google user from session state, if any."""
    user = st.session_state.get("google_user")
    if not isinstance(user, dict):
        return None
    email = user.get("email")
    name = user.get("name")
    google_id = user.get("google_id")
    if not email or not name or not google_id:
        return None
    return user


def logout() -> None:
    """Clear auth-related session state."""
    for key in [
        "google_user",
        "_google_auth_error",
        _AUTH_URL_KEY,
    ]:
        st.session_state.pop(key, None)
    st.query_params.clear()


def get_login_url() -> str | None:
    """Return the Google authorization URL for the current session."""
    return st.session_state.get(_AUTH_URL_KEY)


def get_resolved_redirect_uri() -> str:
    """Return the resolved redirect URI used for Google OAuth."""
    return _get_redirect_uri()


def _handle_callback(code: str, signed_state: str | None) -> None:
    _, client_secret = _get_google_credentials()
    if not _is_valid_signed_state(signed_state, client_secret):
        st.session_state["_google_auth_error"] = (
            "OAuth callback state could not be verified before token exchange. "
            "Please try signing in again."
        )
        st.query_params.clear()
        return

    try:
        flow = _build_flow()
        flow.fetch_token(code=code)
        user_info = (
            build("oauth2", "v2", credentials=flow.credentials)
            .userinfo()
            .get()
            .execute()
        )
    except Exception as exc:
        st.session_state["_google_auth_error"] = str(exc)
        st.query_params.clear()
        return

    st.session_state["google_user"] = {
        "email": user_info.get("email"),
        "name": user_info.get("name"),
        "google_id": user_info.get("id"),
    }
    st.session_state.pop("_google_auth_error", None)
    st.query_params.clear()
    st.rerun()


def _build_flow(state: str | None = None) -> Flow:
    client_id, client_secret = _get_google_credentials()
    return Flow.from_client_config(
        client_config={
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "redirect_uris": [
                    "http://localhost:8501",
                    "https://uoft-agent.streamlit.app",
                ],
            }
        },
        scopes=_SCOPES,
        redirect_uri=_get_redirect_uri(),
        state=state,
        autogenerate_code_verifier=False,
    )


def _get_google_credentials() -> tuple[str, str]:
    try:
        client_id = st.secrets.get("GOOGLE_CLIENT_ID")
        client_secret = st.secrets.get("GOOGLE_CLIENT_SECRET")
    except StreamlitSecretNotFoundError:
        client_id = None
        client_secret = None

    client_id = client_id or os.getenv("GOOGLE_CLIENT_ID")
    client_secret = client_secret or os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured")
    return client_id, client_secret


def _get_redirect_uri() -> str:
    try:
        redirect_uri = st.secrets.get("REDIRECT_URI")
    except StreamlitSecretNotFoundError:
        redirect_uri = None

    redirect_uri = redirect_uri or os.getenv("REDIRECT_URI")
    if redirect_uri:
        return redirect_uri.rstrip("/")

    try:
        has_secrets = bool(st.secrets.get("GOOGLE_CLIENT_ID"))
    except StreamlitSecretNotFoundError:
        has_secrets = False

    if has_secrets:
        return "https://uoft-agent.streamlit.app"
    return "http://localhost:8501"


def _build_signed_state(secret: str) -> str:
    payload = {
        "nonce": secrets.token_urlsafe(24),
    }
    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8").rstrip("=")
    signature = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    return f"{payload_b64}.{signature_b64}"


def _is_valid_signed_state(signed_state: str | None, secret: str) -> bool:
    if not signed_state or "." not in signed_state:
        return False
    payload_b64, signature_b64 = signed_state.split(".", 1)
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected_signature_b64 = base64.urlsafe_b64encode(expected_signature).decode("utf-8").rstrip("=")
    if not hmac.compare_digest(signature_b64, expected_signature_b64):
        return False

    try:
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
    except Exception:
        return False
    return bool(payload.get("nonce"))
