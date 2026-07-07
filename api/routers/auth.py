"""
api/routers/auth.py - Google OAuth auth routes.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from fastapi.responses import JSONResponse, RedirectResponse

from api.dependencies import get_current_user
from api.services.auth_service import (
    AuthServiceError,
    build_google_oauth_url,
    create_access_token,
    exchange_google_code,
    get_or_create_backend_user,
    login_with_password,
    reset_password,
    send_password_reset,
    signup_with_password,
)

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)


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


@router.get("/google")
def google_oauth_redirect(request: Request):
    try:
        redirect_uri = _redirect_uri(request)
        target = build_google_oauth_url(redirect_uri)
    except AuthServiceError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    logger.info("Google OAuth redirect_uri: %s", redirect_uri)
    logger.info("Google OAuth URL: %s", target)
    return RedirectResponse(target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/callback", name="auth_callback")
def google_oauth_callback(request: Request, code: str):
    try:
        redirect_uri = _redirect_uri(request)
        logger.info("Google OAuth callback redirect_uri: %s", redirect_uri)
        google_userinfo = exchange_google_code(code, redirect_uri)
        user = get_or_create_backend_user(google_userinfo)
        token = create_access_token(user)
    except AuthServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    frontend_redirect = _frontend_callback_url(token)
    logger.info("Frontend auth callback URL: %s", frontend_redirect)
    return RedirectResponse(frontend_redirect, status_code=status.HTTP_302_FOUND)


@router.post("/signup")
async def password_signup(payload: PasswordSignupRequest):
    try:
        signup_with_password(payload.email, payload.password)
    except AuthServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True, "message": "Check your email to verify your account before signing in."}


@router.post("/login")
async def password_login(payload: PasswordLoginRequest):
    try:
        user = login_with_password(payload.email, payload.password)
        token = create_access_token(user)
    except AuthServiceError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return {"token": token, "user": user}


@router.post("/password/forgot")
async def forgot_password(payload: ForgotPasswordRequest):
    try:
        send_password_reset(payload.email)
    except AuthServiceError:
        logger.info("Password reset request failed for submitted email")
    return {"ok": True, "message": "If an account exists for that email, a reset link has been sent."}


@router.post("/password/reset")
async def complete_password_reset(payload: ResetPasswordRequest):
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
    logger.info(
        "Auth /me user_id=%s email=%s name=%s google_id=%s",
        current_user.get("user_id"),
        current_user.get("email"),
        current_user.get("name"),
        current_user.get("google_id"),
    )
    return current_user
