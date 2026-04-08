"""
auth/google_auth.py — Google OAuth helpers for Streamlit.
"""

from __future__ import annotations

import json
import os
import tempfile
import traceback
from pathlib import Path

try:
    import streamlit as st
except Exception:
    print("Failed to import streamlit in auth.google_auth", flush=True)
    traceback.print_exc()
    raise

try:
    from streamlit.errors import StreamlitSecretNotFoundError
except Exception:
    print("Failed to import StreamlitSecretNotFoundError in auth.google_auth", flush=True)
    traceback.print_exc()
    raise

try:
    import streamlit_google_auth
    from streamlit_google_auth import Authenticate
except Exception:
    print("Failed to import streamlit_google_auth.Authenticate in auth.google_auth", flush=True)
    traceback.print_exc()
    raise

_COOKIE_NAME = "uoft_agent_auth"
_AUTH_ERROR_KEY = "_google_auth_error"
_AUTH_INSTANCE: Authenticate | None = None
_FLOW_PATCHED = False


def init_google_auth() -> None:
    """Initialise the Google OAuth flow and process any callback."""
    _ensure_auth_session_state()
    st.session_state.pop(_AUTH_ERROR_KEY, None)
    try:
        auth = _build_authenticator()
        auth.check_authentification()
    except Exception as exc:
        st.session_state[_AUTH_ERROR_KEY] = str(exc)
        print("Google OAuth initialisation failed", flush=True)
        traceback.print_exc()
        raise


def render_google_login_button() -> None:
    """Render the Google login button using streamlit-google-auth."""
    _ensure_auth_session_state()
    try:
        auth = _build_authenticator()
        auth.login()
    except Exception as exc:
        st.session_state[_AUTH_ERROR_KEY] = str(exc)
        print("Google OAuth login button rendering failed", flush=True)
        traceback.print_exc()
        raise


def get_logged_in_user() -> dict | None:
    """Return the logged-in Google user from session state, if any."""
    if not st.session_state.get("connected"):
        return None

    user_info = st.session_state.get("user_info")
    if not isinstance(user_info, dict):
        return None

    email = user_info.get("email")
    name = user_info.get("name")
    google_id = user_info.get("id") or st.session_state.get("oauth_id")
    if not email or not name or not google_id:
        return None

    return {
        "email": email,
        "name": name,
        "google_id": google_id,
    }


def get_auth_error() -> str | None:
    """Return the latest auth error, if any."""
    error = st.session_state.get(_AUTH_ERROR_KEY)
    return str(error) if error else None


def logout() -> None:
    """Clear auth-related session state and cookies."""
    auth = _build_authenticator()
    try:
        auth.logout()
    finally:
        for key in [
            _AUTH_ERROR_KEY,
            "connected",
            "user_info",
            "oauth_id",
            "logout",
            "name",
            "username",
        ]:
            st.session_state.pop(key, None)
        st.query_params.clear()


def get_resolved_redirect_uri() -> str:
    """Return the resolved redirect URI used for Google OAuth."""
    return _get_redirect_uri()


def _build_authenticator() -> Authenticate:
    global _AUTH_INSTANCE
    _ensure_auth_session_state()
    if _AUTH_INSTANCE is not None:
        return _AUTH_INSTANCE

    _patch_streamlit_google_auth_flow()
    client_id, client_secret = _get_google_credentials()
    cookie_secret = _get_cookie_secret()
    redirect_uri = _get_redirect_uri()
    credentials_path = _write_client_secrets_file(client_id, client_secret)
    print(f"Google OAuth redirect_uri: {redirect_uri}", flush=True)
    _AUTH_INSTANCE = Authenticate(
        secret_credentials_path=str(credentials_path),
        cookie_name=_COOKIE_NAME,
        cookie_key=cookie_secret,
        redirect_uri=redirect_uri,
    )
    return _AUTH_INSTANCE


def _ensure_auth_session_state() -> None:
    st.session_state.setdefault("connected", False)
    st.session_state.setdefault("user_info", None)
    st.session_state.setdefault("oauth_id", None)


def _patch_streamlit_google_auth_flow() -> None:
    global _FLOW_PATCHED
    if _FLOW_PATCHED:
        return

    flow_cls = streamlit_google_auth.google_auth_oauthlib.flow.Flow
    original = flow_cls.from_client_secrets_file

    def _from_client_secrets_file_no_pkce(*args, **kwargs):
        kwargs.setdefault("autogenerate_code_verifier", False)
        return original(*args, **kwargs)

    flow_cls.from_client_secrets_file = _from_client_secrets_file_no_pkce
    _FLOW_PATCHED = True
    print("Patched streamlit-google-auth Flow to disable PKCE", flush=True)


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


def _get_cookie_secret() -> str:
    try:
        cookie_secret = st.secrets.get("COOKIE_SECRET")
    except StreamlitSecretNotFoundError:
        cookie_secret = None

    cookie_secret = cookie_secret or os.getenv("COOKIE_SECRET")
    if not cookie_secret:
        raise RuntimeError("COOKIE_SECRET must be configured")
    return str(cookie_secret)


def _get_redirect_uri() -> str:
    try:
        redirect_uri = st.secrets.get("REDIRECT_URI")
    except StreamlitSecretNotFoundError:
        redirect_uri = None

    redirect_uri = redirect_uri or os.getenv("REDIRECT_URI")
    if redirect_uri:
        return str(redirect_uri).rstrip("/")

    try:
        has_secrets = bool(st.secrets.get("GOOGLE_CLIENT_ID"))
    except StreamlitSecretNotFoundError:
        has_secrets = False

    if has_secrets:
        return "https://uoft-agent.streamlit.app"
    return "http://localhost:8501"


def _write_client_secrets_file(client_id: str, client_secret: str) -> Path:
    payload = {
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
    }

    path = Path(tempfile.gettempdir()) / "uoft_agent_google_oauth_client.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
