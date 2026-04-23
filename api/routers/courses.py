"""
api/routers/courses.py - Course, grade, scenario, weight, and token routes.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from api.dependencies import get_current_user
from api.services.course_service import (
    CourseServiceError,
    QuercusError,
    get_dashboard_announcements,
    get_dashboard_course,
    get_course_grades,
    get_latest_course_announcement,
    get_course_scenarios,
    get_course_weights,
    list_current_term_courses,
)
from api.services.grades_snapshot_service import GradesSnapshotServiceError, save_snapshot
from auth.user_store import (
    UserStoreError,
    delete_quercus_token,
    get_quercus_token,
    save_quercus_token,
)

router = APIRouter(tags=["courses"])
logger = logging.getLogger(__name__)


class QuercusTokenBody(BaseModel):
    token: str


def _token_debug_value(token: str | None) -> str:
    if not token:
        return "<missing>"
    if len(token) <= 10:
        return token
    return f"{token[:6]}...{token[-4:]} (len={len(token)})"


def _resolve_token(
    quercus_token: str | None,
    current_user: dict,
) -> str:
    """Return the caller-supplied token or fall back to the saved one."""
    if quercus_token:
        logger.info(
            "Resolved dashboard token from request user_id=%s token=%s",
            current_user.get("user_id"),
            _token_debug_value(quercus_token),
        )
        return quercus_token
    try:
        saved = get_quercus_token(current_user["user_id"])
    except UserStoreError as exc:
        logger.exception(
            "Failed to load saved Quercus token user_id=%s",
            current_user.get("user_id"),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not saved:
        logger.warning(
            "No saved Quercus token found user_id=%s",
            current_user.get("user_id"),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Quercus token provided and no saved token found. "
                   "Pass ?quercus_token=... or save one via POST /api/quercus-token.",
        )
    logger.info(
        "Resolved dashboard token from saved Supabase token user_id=%s token=%s",
        current_user.get("user_id"),
        _token_debug_value(saved),
    )
    return saved


# ---------------------------------------------------------------------------
# Quercus token management
# ---------------------------------------------------------------------------

@router.get("/quercus-token", dependencies=[Depends(get_current_user)])
def read_quercus_token(current_user: dict = Depends(get_current_user)):
    try:
        token = get_quercus_token(current_user["user_id"])
    except UserStoreError as exc:
        logger.exception(
            "Failed to read saved Quercus token user_id=%s error=%s",
            current_user.get("user_id"),
            exc,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if token is None:
        logger.info("No saved Quercus token for user_id=%s", current_user.get("user_id"))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No saved Quercus token")
    logger.info(
        "Read saved Quercus token user_id=%s token=%s",
        current_user.get("user_id"),
        _token_debug_value(token),
    )
    return {"token": token}


@router.post("/quercus-token", dependencies=[Depends(get_current_user)])
def write_quercus_token(
    body: QuercusTokenBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        save_quercus_token(current_user["user_id"], body.token)
    except UserStoreError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"status": "saved"}


@router.delete("/quercus-token", dependencies=[Depends(get_current_user)])
def remove_quercus_token(current_user: dict = Depends(get_current_user)):
    try:
        delete_quercus_token(current_user["user_id"])
    except UserStoreError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Course data routes  (token from query param or saved fallback)
# ---------------------------------------------------------------------------

@router.get("")
def list_courses(
    quercus_token: str | None = Query(default=None, description="Quercus personal access token"),
    current_user: dict = Depends(get_current_user),
):
    token = _resolve_token(quercus_token, current_user)
    try:
        return {"courses": list_current_term_courses(token)}
    except (CourseServiceError, QuercusError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/dashboard")
async def dashboard_courses(
    quercus_token: str | None = Query(default=None, description="Quercus personal access token"),
    current_user: dict = Depends(get_current_user),
):
    token = _resolve_token(quercus_token, current_user)
    try:
        logger.info(
            "Starting dashboard load user_id=%s token=%s",
            current_user.get("user_id"),
            _token_debug_value(token),
        )
        courses = list_current_term_courses(token)
        tasks = [asyncio.to_thread(get_dashboard_course, token, course) for course in courses]
        dashboard = await asyncio.gather(*tasks)
        announcements = await asyncio.to_thread(get_dashboard_announcements, token, courses)
        try:
            await asyncio.to_thread(save_snapshot, current_user["user_id"], dashboard)
        except GradesSnapshotServiceError as exc:
            logger.warning(
                "Failed to persist grades snapshot user_id=%s error=%s",
                current_user.get("user_id"),
                exc,
            )
        logger.info(
            "Completed dashboard load user_id=%s courses=%s announcements=%s",
            current_user.get("user_id"),
            len(dashboard),
            len(announcements),
        )
        return {"courses": dashboard, "announcements": announcements}
    except (CourseServiceError, QuercusError) as exc:
        logger.exception(
            "Dashboard load failed user_id=%s token=%s error=%s",
            current_user.get("user_id"),
            _token_debug_value(token),
            exc,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "Unexpected dashboard load failure user_id=%s token=%s error=%s",
            current_user.get("user_id"),
            _token_debug_value(token),
            exc,
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected dashboard error") from exc


@router.get("/{course_id}/grades")
def course_grades(
    course_id: int,
    quercus_token: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    token = _resolve_token(quercus_token, current_user)
    try:
        return get_course_grades(token, course_id)
    except (CourseServiceError, QuercusError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{course_id}/announcements/latest")
def latest_course_announcement(
    course_id: int,
    quercus_token: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    token = _resolve_token(quercus_token, current_user)
    try:
        return get_latest_course_announcement(token, course_id)
    except (CourseServiceError, QuercusError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{course_id}/scenarios")
def course_scenarios(
    course_id: int,
    quercus_token: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    token = _resolve_token(quercus_token, current_user)
    try:
        return get_course_scenarios(token, course_id)
    except (CourseServiceError, QuercusError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{course_id}/weights")
def course_weights(
    course_id: int,
    quercus_token: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    token = _resolve_token(quercus_token, current_user)
    try:
        return get_course_weights(token, course_id)
    except (CourseServiceError, QuercusError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
