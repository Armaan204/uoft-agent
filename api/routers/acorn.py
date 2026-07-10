"""
api/routers/acorn.py - ACORN import routes with exact api_server.py contract.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, UploadFile
from fastapi.responses import JSONResponse

from api.dependencies import get_current_user
from api.integrations.acorn_pdf_parser import AcornPdfParseError, parse_acorn_pdf
from api.services.acorn_service import (
    AcornServiceError,
    claim_latest_import_for_user,
    get_latest_import_for_user,
    store_acorn_pdf_import,
)
from api.integrations.acorn_store import AcornStoreError

router = APIRouter(tags=["acorn"])
logger = logging.getLogger(__name__)


@router.get("/me")
def my_latest_import(current_user: dict = Depends(get_current_user)):
    try:
        latest = get_latest_import_for_user(current_user["user_id"])
    except (AcornStoreError, AcornServiceError) as exc:
        logger.exception("ACORN user lookup failed user_id=%s", current_user.get("user_id"))
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to load ACORN data"})
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
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to claim ACORN import"})

    return JSONResponse(status_code=200, content={"ok": True, "data": latest})


@router.post("/upload")
async def upload_acorn_pdf(
    file: UploadFile,
    current_user: dict = Depends(get_current_user),
):
    filename = (file.filename or "").lower()
    if not filename.endswith(".pdf"):
        return JSONResponse(status_code=400, content={"ok": False, "error": "Only PDF files are accepted"})

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        return JSONResponse(status_code=400, content={"ok": False, "error": "File exceeds 10 MB limit"})

    if not content[:5].startswith(b"%PDF-"):
        return JSONResponse(status_code=400, content={"ok": False, "error": "File does not appear to be a valid PDF"})

    try:
        parsed = parse_acorn_pdf(content)
    except AcornPdfParseError as exc:
        logger.exception("ACORN PDF parse error")
        return JSONResponse(status_code=400, content={"ok": False, "error": "Failed to parse the uploaded PDF. Please ensure it is a valid ACORN Complete Academic History PDF."})

    try:
        stored = store_acorn_pdf_import(current_user["user_id"], parsed)
    except AcornServiceError as exc:
        logger.exception("ACORN PDF storage error")
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to save ACORN data"})

    return JSONResponse(status_code=200, content={"ok": True, "data": stored})
