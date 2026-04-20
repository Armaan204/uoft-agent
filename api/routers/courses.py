"""
api/routers/courses.py - Course, grade, scenario, weight, and token routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from api.dependencies import get_current_user
from api.services.course_service import (
    CourseServiceError,
    QuercusError,
    get_course_grades,
    get_course_scenarios,
    get_course_weights,
    list_current_term_courses,
)
from auth.user_store import (
    UserStoreError,
    delete_quercus_token,
    get_quercus_token,
    save_quercus_token,
)

router = APIRouter(tags=["courses"])


class QuercusTokenBody(BaseModel):
    token: str


def _resolve_token(
    quercus_token: str | None,
    current_user: dict,
) -> str:
    """Return the caller-supplied token or fall back to the saved one."""
    if quercus_token:
        return quercus_token
    try:
        saved = get_quercus_token(current_user["user_id"])
    except UserStoreError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not saved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Quercus token provided and no saved token found. "
                   "Pass ?quercus_token=... or save one via POST /api/quercus-token.",
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No saved Quercus token")
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
