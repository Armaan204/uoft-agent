"""
api/routers/manual_courses.py — CRUD routes for manually added courses and deadlines.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel

from api.dependencies import get_current_user
from api.services.manual_course_service import (
    ManualCourseServiceError,
    create_manual_course,
    create_manual_deadline,
    delete_manual_course,
    delete_manual_deadline,
    get_manual_course,
    list_manual_courses,
    list_manual_deadlines,
    update_manual_course,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["manual-courses"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CreateCourseBody(BaseModel):
    course_code: str
    course_name: str
    term: str = ""
    weights: dict[str, float] | None = None


class UpdateCourseBody(BaseModel):
    course_code: str | None = None
    course_name: str | None = None
    term: str | None = None
    weights: dict[str, float] | None = None
    syllabus_source: str | None = None


class CreateDeadlineBody(BaseModel):
    course_id: int | None = None
    course_code: str = ""
    name: str
    due_at: str


# ---------------------------------------------------------------------------
# Course CRUD
# ---------------------------------------------------------------------------

@router.post("")
def create_course(
    body: CreateCourseBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        course = create_manual_course(
            user_id=current_user["user_id"],
            course_code=body.course_code,
            course_name=body.course_name,
            term=body.term,
            weights=body.weights,
        )
    except ManualCourseServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return course


@router.get("")
def list_courses(current_user: dict = Depends(get_current_user)):
    try:
        return list_manual_courses(current_user["user_id"])
    except ManualCourseServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/{course_id}")
def update_course(
    course_id: int,
    body: UpdateCourseBody,
    current_user: dict = Depends(get_current_user),
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")
    try:
        return update_manual_course(current_user["user_id"], course_id, updates)
    except ManualCourseServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{course_id}")
def delete_course(
    course_id: int,
    current_user: dict = Depends(get_current_user),
):
    try:
        delete_manual_course(current_user["user_id"], course_id)
    except ManualCourseServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True}


# ---------------------------------------------------------------------------
# Syllabus upload
# ---------------------------------------------------------------------------

@router.post("/{course_id}/syllabus")
async def upload_syllabus(
    course_id: int,
    file: UploadFile,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]

    course = get_manual_course(user_id, course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual course not found")

    filename = (file.filename or "").lower()
    if not filename.endswith((".pdf", ".docx")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF and DOCX files are supported",
        )

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size must be under 10 MB",
        )

    is_pdf = content[:5].startswith(b"%PDF-")
    is_docx = content[:4] == b"PK\x03\x04"
    if filename.endswith(".pdf") and not is_pdf:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File does not appear to be a valid PDF",
        )
    if filename.endswith(".docx") and not is_docx:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File does not appear to be a valid DOCX",
        )

    try:
        if filename.endswith(".pdf"):
            from api.integrations.syllabus import extract_weights_from_bytes
            weights = extract_weights_from_bytes(content)
        else:
            import io
            import docx
            doc = docx.Document(io.BytesIO(content))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            if not text:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="DOCX contained no extractable text",
                )
            from api.integrations.syllabus import _ask_claude
            weights = _ask_claude(text)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Syllabus parsing failed course_id=%s", course_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to extract weights from the uploaded file",
        ) from exc

    return {"weights": weights, "filename": file.filename}


# ---------------------------------------------------------------------------
# Deadline CRUD
# ---------------------------------------------------------------------------

@router.post("/deadlines")
def create_deadline(
    body: CreateDeadlineBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        return create_manual_deadline(
            user_id=current_user["user_id"],
            course_id=body.course_id,
            course_code=body.course_code,
            name=body.name,
            due_at=body.due_at,
        )
    except ManualCourseServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/deadlines")
def get_deadlines(current_user: dict = Depends(get_current_user)):
    try:
        return list_manual_deadlines(current_user["user_id"])
    except ManualCourseServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/deadlines/{deadline_id}")
def remove_deadline(
    deadline_id: int,
    current_user: dict = Depends(get_current_user),
):
    try:
        delete_manual_deadline(current_user["user_id"], deadline_id)
    except ManualCourseServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True}
