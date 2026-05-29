"""
api/routers/admin.py - Local-only admin endpoints for development debugging.

Only mounted when ENVIRONMENT != "production". Never deploy with this active.

Usage:
  1. GET http://localhost:8001/admin/impersonate/<user_id>
  2. Copy the token value from the response
  3. In browser console:
       localStorage.setItem('uoft-agent-token', '<token>')
       location.reload()
  4. The frontend now operates fully as that user (all tabs, cache, etc.)
  5. To restore your own account:
       localStorage.removeItem('uoft-agent-token')
     then log in normally via the login page
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from api.services.auth_service import create_access_token
from api.auth.user_store import UserStoreError, get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/impersonate/{user_id}")
def impersonate_user(user_id: str):
    try:
        response = (
            get_supabase_client()
            .table("users")
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except (UserStoreError, Exception) as exc:
        raise HTTPException(status_code=500, detail=f"Supabase lookup failed: {exc}") from exc

    rows = getattr(response, "data", None) or []
    if not rows:
        raise HTTPException(status_code=404, detail=f"No user found with id={user_id!r}")

    user = rows[0]
    token = create_access_token(user)
    logger.warning(
        "IMPERSONATION TOKEN ISSUED for user_id %s (%s)",
        user_id,
        user.get("email"),
    )
    return {
        "token": token,
        "user": {
            "id": user.get("id"),
            "email": user.get("email"),
            "google_id": user.get("google_id"),
        },
    }
