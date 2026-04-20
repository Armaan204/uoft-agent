"""
api/routers/auth.py - Google OAuth auth routes.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from api.dependencies import get_current_user
from api.services.auth_service import (
    AuthServiceError,
    build_google_oauth_url,
    create_access_token,
    exchange_google_code,
    get_or_create_backend_user,
)

router = APIRouter(tags=["auth"])


def _redirect_uri(request: Request) -> str:
    return os.getenv("GOOGLE_REDIRECT_URI") or str(request.url_for("auth_callback"))


@router.get("/google")
def google_oauth_redirect(request: Request):
    try:
        target = build_google_oauth_url(_redirect_uri(request))
    except AuthServiceError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return RedirectResponse(target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/callback", name="auth_callback")
def google_oauth_callback(request: Request, code: str):
    try:
        google_userinfo = exchange_google_code(code, _redirect_uri(request))
        user = get_or_create_backend_user(google_userinfo)
        token = create_access_token(user)
    except AuthServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "token": token,
        "user": {
            "user_id": user.get("id"),
            "email": user.get("email"),
            "google_id": user.get("google_id"),
        },
    }


@router.post("/logout")
def logout():
    return JSONResponse({"ok": True, "message": "Client should discard the token"})


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return current_user
