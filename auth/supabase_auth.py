"""
auth/supabase_auth.py — Supabase Auth helpers for Streamlit.

Flow:
  1. Login page calls get_google_login_url() → generates Supabase OAuth URL
     with a PKCE code_verifier cached in session state; renders an st.link_button.
  2. Supabase handles Google OAuth and redirects back to the app with ?code=...
  3. init_auth() (called at top of main on every render) detects the code,
     exchanges it for a session via exchange_code_for_session, stores the user
     in session state, and clears the query param.
  4. get_logged_in_user() returns the stored user dict, or None if not logged in.
  5. logout() wipes all auth keys from session state.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import threading
import time
import traceback
from urllib.parse import urlencode

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from supabase import create_client, Client


_SESSION_KEY = "supabase_auth_session"
_CODE_PROCESSED_KEY = "_supabase_code_processed"
_LOGIN_URL_KEY = "_supabase_login_url"
_AUTH_ERROR_KEY = "_supabase_auth_error"

# ---------------------------------------------------------------------------
# Module-level PKCE store
#
# st.session_state is per browser-session and is lost when OAuth navigates
# the user away from the app (the callback arrives in a fresh session).
# We store the pending PKCE verifier at module level so it survives across
# sessions within the same process.  A TTL of 5 minutes is generous —
# the whole OAuth round-trip takes a few seconds.
# ---------------------------------------------------------------------------

_PKCE_LOCK = threading.Lock()
_PENDING_PKCE: tuple[str, float] | None = None  # (code_verifier, expires_monotonic)
_PKCE_TTL = 300.0  # seconds


def _pkce_set(verifier: str) -> None:
    global _PENDING_PKCE
    with _PKCE_LOCK:
        _PENDING_PKCE = (verifier, time.monotonic() + _PKCE_TTL)


def _pkce_pop() -> str | None:
    """Consume and return the pending verifier, or None if absent/expired."""
    global _PENDING_PKCE
    with _PKCE_LOCK:
        entry = _PENDING_PKCE
        _PENDING_PKCE = None
    if entry and entry[1] > time.monotonic():
        return entry[0]
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) per RFC 7636 S256."""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return code_verifier, code_challenge


def _get_secret(name: str) -> str | None:
    try:
        val = st.secrets.get(name)
    except StreamlitSecretNotFoundError:
        val = None
    return val or os.getenv(name) or None


def _get_supabase_client() -> Client:
    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be configured")
    return create_client(url, key)


def _get_app_url() -> str:
    """Return the redirect URL that Supabase will send the user back to."""
    redirect_uri = _get_secret("REDIRECT_URI")
    if redirect_uri:
        return redirect_uri.rstrip("/")
    # On Streamlit Cloud, st.secrets will contain SUPABASE_URL; use that as
    # the production-environment signal.
    try:
        is_cloud = bool(st.secrets.get("SUPABASE_URL"))
    except StreamlitSecretNotFoundError:
        is_cloud = False
    return "https://uoft-agent.streamlit.app" if is_cloud else "http://localhost:8501"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_google_login_url() -> str:
    """Return the Supabase Google OAuth URL, generating it once per session.

    We generate the PKCE pair ourselves (RFC 7636 S256) rather than
    relying on the gotrue-py client to surface the code_verifier — the
    Python client does not reliably return it on all versions.  The
    code_verifier is stored in session state; the matching code_challenge
    is embedded in the authorization URL.
    """
    if _LOGIN_URL_KEY in st.session_state:
        return st.session_state[_LOGIN_URL_KEY]

    supabase_url = (_get_secret("SUPABASE_URL") or "").rstrip("/")
    app_url = _get_app_url()

    code_verifier, code_challenge = _generate_pkce_pair()
    _pkce_set(code_verifier)  # survive session change during OAuth redirect

    params = {
        "provider": "google",
        "redirect_to": app_url,
        "code_challenge": code_challenge,
        "code_challenge_method": "s256",
        "prompt": "select_account",  # always show Google account picker
    }
    url = f"{supabase_url}/auth/v1/authorize?{urlencode(params)}"
    st.session_state[_LOGIN_URL_KEY] = url
    print(f"Supabase OAuth URL generated (redirect_to={app_url})", flush=True)
    return url


def init_auth() -> None:
    """Process the Supabase OAuth callback if a ?code= query param is present.

    Safe to call unconditionally at the top of main() — exits immediately
    when no code is present or the code has already been processed.
    On success, stores the authenticated session in st.session_state.
    On failure, stores an error message for the login page to display.
    """
    code = st.query_params.get("code")
    if not code:
        return

    # Guard: Streamlit reruns the script on every interaction, so the ?code=
    # may still be in the URL after we've already processed it.
    if st.session_state.get(_CODE_PROCESSED_KEY) == code:
        st.query_params.clear()
        return

    st.session_state.pop(_AUTH_ERROR_KEY, None)

    try:
        supabase = _get_supabase_client()
        # Verifier is stored module-level because the OAuth redirect creates a
        # new Streamlit session and session_state is lost between sessions.
        code_verifier = _pkce_pop()

        exchange_params: dict = {"auth_code": code}
        if code_verifier:
            exchange_params["code_verifier"] = code_verifier

        auth_response = supabase.auth.exchange_code_for_session(exchange_params)
        user = auth_response.user
        session = auth_response.session

        metadata = user.user_metadata or {}
        name = (
            metadata.get("full_name")
            or metadata.get("name")
            or user.email
        )

        st.session_state[_SESSION_KEY] = {
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "user": {"id": user.id, "email": user.email, "name": name},
        }
        print(f"Supabase auth: session established for {user.email}", flush=True)

    except Exception as exc:
        print(f"Supabase OAuth code exchange failed: {exc}", flush=True)
        traceback.print_exc()
        st.session_state.pop(_SESSION_KEY, None)
        st.session_state[_AUTH_ERROR_KEY] = str(exc)

    finally:
        # Mark this code as processed and clean up one-time keys regardless
        # of whether the exchange succeeded.
        st.session_state[_CODE_PROCESSED_KEY] = code
        st.session_state.pop(_LOGIN_URL_KEY, None)
        st.query_params.clear()


def get_logged_in_user() -> dict | None:
    """Return {id, email, name} for the authenticated user, or None."""
    session = st.session_state.get(_SESSION_KEY)
    if not session:
        return None
    return session.get("user")


def get_auth_error() -> str | None:
    """Return the latest auth error message, if any."""
    error = st.session_state.get(_AUTH_ERROR_KEY)
    return str(error) if error else None


def logout() -> None:
    """Clear all Supabase auth state from the Streamlit session."""
    for key in (_SESSION_KEY, _CODE_PROCESSED_KEY, _LOGIN_URL_KEY, _AUTH_ERROR_KEY):
        st.session_state.pop(key, None)
    _pkce_pop()  # discard any pending verifier
