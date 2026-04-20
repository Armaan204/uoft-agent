"""
api/routers/courses.py - Course, grade, scenario, and weight routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_current_user
from api.services.course_service import (
    CourseServiceError,
    QuercusError,
    get_course_grades,
    get_course_scenarios,
    get_course_weights,
    get_user_quercus_token,
    list_current_term_courses,
)

router = APIRouter(tags=["courses"], dependencies=[Depends(get_current_user)])


@router.get("")
def list_courses(current_user: dict = Depends(get_current_user)):
    try:
        token = get_user_quercus_token(current_user["user_id"])
        return {"courses": list_current_term_courses(token)}
    except (CourseServiceError, QuercusError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{course_id}/grades")
def course_grades(course_id: int, current_user: dict = Depends(get_current_user)):
    try:
        token = get_user_quercus_token(current_user["user_id"])
        return get_course_grades(token, course_id)
    except (CourseServiceError, QuercusError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{course_id}/scenarios")
def course_scenarios(course_id: int, current_user: dict = Depends(get_current_user)):
    try:
        token = get_user_quercus_token(current_user["user_id"])
        return get_course_scenarios(token, course_id)
    except (CourseServiceError, QuercusError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{course_id}/weights")
def course_weights(course_id: int, current_user: dict = Depends(get_current_user)):
    try:
        token = get_user_quercus_token(current_user["user_id"])
        return get_course_weights(token, course_id)
    except (CourseServiceError, QuercusError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
