"""
api/routers/graduation.py — Graduation progress routes.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_current_user
from api.services.acorn_service import AcornServiceError, get_academic_history
from api.integrations.course_exclusions import fetch_exclusions_batch
from api.integrations.graduation_service import (
    check_graduation_progress,
    clear_cache,
    collect_required_courses,
    get_program_requirements,
)

router = APIRouter(tags=["graduation"])
logger = logging.getLogger(__name__)


def _student_codes(acorn_data: dict) -> list[str]:
    """Extract all course codes from an ACORN academic history dict."""
    raw: list[dict] = []
    for term in acorn_data.get("terms", []):
        raw.extend(term.get("courses", []))
    if not raw:
        raw = acorn_data.get("courses", [])
    return [
        (c.get("code") or c.get("courseCode") or "").strip().upper()
        for c in raw
        if (c.get("code") or c.get("courseCode") or "").strip()
    ]


@router.get("/progress")
async def graduation_progress(
    force_refresh: bool = Query(default=False, description="Re-extract requirements even if cached"),
    current_user: dict = Depends(get_current_user),
):
    """
    Return the authenticated user's graduation progress for all enrolled programs.

    Returns a list of progress objects, one per program. On first call this may
    take 10-30 s per program while requirements are discovered and extracted from
    the calendar. Subsequent calls return cached results instantly.
    """
    user_id = current_user["user_id"]

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

    async def fetch_one(prog: dict) -> dict | None:
        name = (prog.get("programName") or "").strip()
        if not name:
            return None
        try:
            requirements = await asyncio.to_thread(get_program_requirements, name, force_refresh)
        except Exception as exc:
            logger.exception("graduation requirements error user=%s program=%s", user_id, name)
            return {"error": f"Requirements extraction error: {exc}", "program_name": name}
        if requirements is None:
            return {"error": f"Could not find calendar requirements for: {name}", "program_name": name}

        # Fetch exclusion lists for all student courses + all explicitly listed required
        # courses so the matcher can resolve cross-campus equivalencies bidirectionally.
        all_codes = list({*_student_codes(acorn_data), *collect_required_courses(requirements)})
        try:
            exclusions_map = await fetch_exclusions_batch(all_codes)
        except Exception:
            exclusions_map = {}

        try:
            progress = await asyncio.to_thread(
                check_graduation_progress, requirements, acorn_data, exclusions_map
            )
        except Exception as exc:
            logger.exception("graduation progress error user=%s program=%s", user_id, name)
            return {"error": f"Progress computation error: {exc}", "program_name": name}
        return progress

    results = await asyncio.gather(*[fetch_one(p) for p in programs])
    valid = [r for r in results if r is not None]

    if not valid:
        raise HTTPException(
            status_code=404,
            detail="Could not find calendar requirements for any enrolled program.",
        )

    return valid


@router.delete("/cache")
async def clear_graduation_cache(
    current_user: dict = Depends(get_current_user),
):
    """Force re-extraction for all of the current user's programs on the next /progress call."""
    user_id = current_user["user_id"]
    try:
        acorn_data = await asyncio.to_thread(get_academic_history, user_id)
    except AcornServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    programs = acorn_data.get("programs") or []
    if not programs:
        raise HTTPException(status_code=400, detail="No ACORN program data found.")

    cleared = []
    for prog in programs:
        name = (prog.get("programName") or "").strip()
        if name:
            await asyncio.to_thread(clear_cache, name)
            cleared.append(name)

    return {"ok": True, "cleared": cleared}
