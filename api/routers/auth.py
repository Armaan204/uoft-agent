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
from api.auth.user_store import UserStoreError
from api.services.auth_service import (
    ACCESS_TOKEN_EXPIRY_MINUTES,
    REFRESH_TOKEN_EXPIRY_DAYS,
    AuthServiceError,
    build_google_oauth_url,
    create_access_token,
    create_refresh_token,
    delete_user_account,
    exchange_google_code,
    get_or_create_backend_user,
    login_with_password,
    refresh_access_token,
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


def _is_production() -> bool:
    return os.getenv("ENVIRONMENT") == "production"


def _set_auth_cookies(response, access_token: str, refresh_token_str: str) -> None:
    secure = _is_production()
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=ACCESS_TOKEN_EXPIRY_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token_str,
        max_age=REFRESH_TOKEN_EXPIRY_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/auth/refresh",
    )


def _clear_auth_cookies(response) -> None:
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/auth/refresh")


def _frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")


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
        secure=_is_production(),
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
        access_token = create_access_token(user)
        refresh_token_str = create_refresh_token(user)
    except AuthServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Authentication failed") from exc
    logger.info("OAuth callback completed for user_id=%s", user.get("id"))
    response = RedirectResponse(f"{_frontend_url()}/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("oauth_state")
    _set_auth_cookies(response, access_token, refresh_token_str)
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
        access_token = create_access_token(user)
        refresh_token_str = create_refresh_token(user)
    except AuthServiceError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    response = JSONResponse({"ok": True, "user": user})
    _set_auth_cookies(response, access_token, refresh_token_str)
    return response


@router.post("/refresh")
@limit("10/minute")
async def refresh(request: Request):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")
    try:
        new_access, user = refresh_access_token(token)
    except (AuthServiceError, UserStoreError) as exc:
        response = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Refresh token expired"},
        )
        _clear_auth_cookies(response)
        return response
    response = JSONResponse({"ok": True})
    secure = _is_production()
    response.set_cookie(
        key="access_token",
        value=new_access,
        max_age=ACCESS_TOKEN_EXPIRY_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    return response


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
    response = JSONResponse({"ok": True, "message": "Logged out"})
    _clear_auth_cookies(response)
    return response


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
    response = JSONResponse({"ok": True, "message": "Your account and all associated data have been deleted."})
    _clear_auth_cookies(response)
    return response
