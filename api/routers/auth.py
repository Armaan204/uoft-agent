"""
api/routers/auth.py - Google OAuth auth routes.
"""

import hashlib
import hmac
import logging
import os
import time
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from fastapi.responses import JSONResponse, RedirectResponse

from api.dependencies import get_current_user
from api.limiter import limit
from api.services.auth_service import (
    AuthServiceError,
    build_google_oauth_url,
    create_access_token,
    delete_user_account,
    exchange_google_code,
    get_or_create_backend_user,
    login_with_password,
    reset_password,
    send_password_reset,
    signup_with_password,
)

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

_OAUTH_STATE_MAX_AGE = 600  # 10 minutes


class PasswordSignupRequest(BaseModel):
    email: str
    password: str


class PasswordLoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    access_token: str
    refresh_token: str
    password: str


def _redirect_uri(request: Request) -> str:
    return os.getenv("REDIRECT_URI") or str(request.url_for("auth_callback"))


def _frontend_callback_url(token: str) -> str:
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    return f"{frontend_url}/auth/callback?{urlencode({'token': token})}"


def _oauth_signing_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET must be configured for OAuth state signing")
    return secret


def _sign_state(state: str) -> str:
    secret = _oauth_signing_secret()
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"{state}:{ts}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{state}:{ts}:{sig}"


def _verify_state(cookie_value: str | None, query_state: str | None) -> bool:
    if not cookie_value or not query_state:
        return False
    parts = cookie_value.split(":")
    if len(parts) != 3:
        return False
    stored_state, ts_str, sig = parts
    if stored_state != query_state:
        return False
    try:
        ts = int(ts_str)
    except ValueError:
        return False
    if time.time() - ts > _OAUTH_STATE_MAX_AGE:
        return False
    secret = _oauth_signing_secret()
    expected = hmac.new(secret.encode(), f"{stored_state}:{ts_str}".encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(sig, expected)


@router.get("/google")
def google_oauth_redirect(request: Request):
    try:
        redirect_uri = _redirect_uri(request)
        target, state = build_google_oauth_url(redirect_uri)
    except AuthServiceError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="OAuth configuration error") from exc
    logger.info("Google OAuth redirect initiated")
    response = RedirectResponse(target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    response.set_cookie(
        key="oauth_state",
        value=_sign_state(state),
        max_age=_OAUTH_STATE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=os.getenv("ENVIRONMENT") == "production",
    )
    return response


@router.get("/callback", name="auth_callback")
def google_oauth_callback(request: Request, code: str, state: str | None = None):
    cookie_state = request.cookies.get("oauth_state")
    if not _verify_state(cookie_state, state):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state")

    try:
        redirect_uri = _redirect_uri(request)
        google_userinfo = exchange_google_code(code, redirect_uri)
        user = get_or_create_backend_user(google_userinfo)
        token = create_access_token(user)
    except AuthServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Authentication failed") from exc
    frontend_redirect = _frontend_callback_url(token)
    logger.info("OAuth callback completed for user_id=%s", user.get("id"))
    response = RedirectResponse(frontend_redirect, status_code=status.HTTP_302_FOUND)
    response.delete_cookie("oauth_state")
    return response


@router.post("/signup")
@limit("3/minute")
async def password_signup(request: Request, payload: PasswordSignupRequest):
    try:
        signup_with_password(payload.email, payload.password)
    except AuthServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True, "message": "Check your email to verify your account before signing in."}


@router.post("/login")
@limit("5/minute")
async def password_login(request: Request, payload: PasswordLoginRequest):
    try:
        user = login_with_password(payload.email, payload.password)
        token = create_access_token(user)
    except AuthServiceError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return {"token": token, "user": user}


@router.post("/password/forgot")
@limit("3/minute")
async def forgot_password(request: Request, payload: ForgotPasswordRequest):
    try:
        send_password_reset(payload.email)
    except AuthServiceError:
        logger.info("Password reset request failed for submitted email")
    return {"ok": True, "message": "If an account exists for that email, a reset link has been sent."}


@router.post("/password/reset")
@limit("3/minute")
async def complete_password_reset(request: Request, payload: ResetPasswordRequest):
    try:
        reset_password(payload.access_token, payload.refresh_token, payload.password)
    except AuthServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True, "message": "Password updated. You can now sign in."}


@router.post("/logout")
def logout():
    return JSONResponse({"ok": True, "message": "Client should discard the token"})


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.delete("/account")
def delete_account(current_user: dict = Depends(get_current_user)):
    try:
        delete_user_account(current_user["user_id"])
    except AuthServiceError as exc:
        logger.exception("Account deletion failed user_id=%s", current_user.get("user_id"))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete account") from exc
    return {"ok": True, "message": "Your account and all associated data have been deleted."}
