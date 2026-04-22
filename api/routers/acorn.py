"""
api/routers/acorn.py - ACORN import routes with exact api_server.py contract.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse

from api.dependencies import get_current_user
from api.services.acorn_service import (
    AcornServiceError,
    claim_latest_import_for_user,
    get_import_status,
    get_latest_import,
    get_latest_import_for_user,
    import_acorn_data,
)
from integrations.acorn_store import AcornStoreError

router = APIRouter(tags=["acorn"])
logger = logging.getLogger(__name__)

@router.post("/import")
def import_acorn(payload: dict[str, Any] = Body(...)):
    body = dict(payload or {})
    import_code = body.get("importCode", "")
    body.pop("importCode", None)
    try:
        stored = import_acorn_data(import_code, body)
    except AcornStoreError as exc:
        logger.exception("ACORN import validation/storage error import_code=%s error=%s", import_code, exc)
        return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})
    except AcornServiceError as exc:
        logger.exception("ACORN import service error import_code=%s error=%s", import_code, exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})
    return JSONResponse(status_code=200, content={
        "ok": True,
        "message": "ACORN data imported successfully",
        "importedAt": stored["importedAt"],
        "courseCount": len(stored["courses"]),
    })


@router.get("/latest")
def latest_import(import_code: str | None = Query(None)):
    if not import_code or not import_code.strip():
        return JSONResponse(status_code=400, content={"ok": False, "error": "Missing import_code query parameter"})

    try:
        latest = get_latest_import(import_code)
    except (AcornStoreError, AcornServiceError) as exc:
        logger.exception("ACORN latest lookup failed import_code=%s error=%s", import_code, exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})

    if latest is None:
        return JSONResponse(status_code=200, content={
            "ok": True,
            "exists": False,
            "message": "No ACORN data has been imported yet.",
            "data": None,
        })
    return JSONResponse(status_code=200, content={"ok": True, "exists": True, "data": latest})


@router.get("/status")
def import_status(import_code: str | None = Query(None)):
    if not import_code or not import_code.strip():
        return JSONResponse(status_code=400, content={"ok": False, "error": "Missing import_code query parameter"})

    try:
        status_payload = get_import_status(import_code)
    except (AcornStoreError, AcornServiceError) as exc:
        logger.exception("ACORN status lookup failed import_code=%s error=%s", import_code, exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})
    return JSONResponse(status_code=200, content={"ok": True, **status_payload})


@router.get("/me")
def my_latest_import(current_user: dict = Depends(get_current_user)):
    try:
        latest = get_latest_import_for_user(current_user["user_id"])
    except (AcornStoreError, AcornServiceError) as exc:
        logger.exception("ACORN user lookup failed user_id=%s error=%s", current_user.get("user_id"), exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})
    return JSONResponse(status_code=200, content={"ok": True, "data": latest})


@router.post("/claim")
def claim_import(payload: dict[str, Any] = Body(...), current_user: dict = Depends(get_current_user)):
    import_code = str((payload or {}).get("import_code") or "").strip()
    if not import_code:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Missing import_code in request body"})

    try:
        latest = claim_latest_import_for_user(import_code, current_user["user_id"])
    except (AcornStoreError, AcornServiceError) as exc:
        logger.exception(
            "ACORN claim failed user_id=%s import_code=%s error=%s",
            current_user.get("user_id"),
            import_code,
            exc,
        )
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})

    return JSONResponse(status_code=200, content={"ok": True, "data": latest})
