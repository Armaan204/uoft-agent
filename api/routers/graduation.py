"""
api/routers/graduation.py — Graduation progress routes.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_current_user
from api.services.acorn_service import AcornServiceError, get_academic_history
from integrations.graduation_service import (
    check_graduation_progress,
    clear_cache,
    get_program_requirements,
)

router = APIRouter(tags=["graduation"])
logger = logging.getLogger(__name__)


@router.get("/progress")
async def graduation_progress(
    force_refresh: bool = Query(default=False, description="Re-extract requirements even if cached"),
    current_user: dict = Depends(get_current_user),
):
    """
    Return the authenticated user's graduation progress.

    On first call this may take 10-30 s while the program requirements are
    discovered and extracted from the calendar. Subsequent calls return the
    cached result instantly.
    """
    user_id = current_user["user_id"]

    # Load ACORN academic history
    try:
        acorn_data = await asyncio.to_thread(get_academic_history, user_id)
    except AcornServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    programs = acorn_data.get("programs") or []
    if not programs:
        raise HTTPException(
            status_code=400,
            detail="No ACORN program data found. Import your ACORN academic history first.",
        )

    program_name = (programs[0].get("programName") or "").strip()
    if not program_name:
        raise HTTPException(
            status_code=400,
            detail="Could not determine program name from ACORN data.",
        )

    # Fetch (or extract) requirements
    try:
        requirements = await asyncio.to_thread(
            get_program_requirements, program_name, force_refresh
        )
    except Exception as exc:
        logger.exception("graduation requirements error user=%s program=%s", user_id, program_name)
        raise HTTPException(status_code=500, detail=f"Requirements extraction error: {exc}")

    if requirements is None:
        raise HTTPException(
            status_code=404,
            detail=f"Could not find calendar requirements for: {program_name}",
        )

    # Compute progress
    try:
        progress = await asyncio.to_thread(check_graduation_progress, requirements, acorn_data)
    except Exception as exc:
        logger.exception("graduation progress error user=%s", user_id)
        raise HTTPException(status_code=500, detail=f"Progress computation error: {exc}")

    return progress


@router.delete("/cache")
async def clear_graduation_cache(
    current_user: dict = Depends(get_current_user),
):
    """Force re-extraction for the current user's program on the next /progress call."""
    user_id = current_user["user_id"]
    try:
        acorn_data = await asyncio.to_thread(get_academic_history, user_id)
    except AcornServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    programs = acorn_data.get("programs") or []
    if not programs:
        raise HTTPException(status_code=400, detail="No ACORN program data found.")

    program_name = (programs[0].get("programName") or "").strip()
    if program_name:
        await asyncio.to_thread(clear_cache, program_name)

    return {"ok": True, "cleared": program_name}
