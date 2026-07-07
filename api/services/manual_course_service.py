"""
api/services/manual_course_service.py — CRUD for manually added courses and deadlines.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

from supabase import Client, create_client

logger = logging.getLogger(__name__)


class ManualCourseServiceError(RuntimeError):
    """Raised when manual course operations fail."""


def _get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ManualCourseServiceError("SUPABASE_URL and SUPABASE_KEY must be configured")
    return create_client(url, key)


def _to_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _row_to_course(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "user_id": row["user_id"],
        "course_code": row["course_code"],
        "course_name": row["course_name"],
        "term": row.get("term", ""),
        "weights": row.get("weights") or {},
        "syllabus_source": row.get("syllabus_source"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _row_to_deadline(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "user_id": row["user_id"],
        "course_id": int(row["course_id"]) if row.get("course_id") is not None else None,
        "course_code": row.get("course_code", ""),
        "name": row["name"],
        "due_at": row["due_at"],
        "created_at": row.get("created_at"),
    }


def create_manual_course(
    user_id: str,
    course_code: str,
    course_name: str,
    term: str = "",
    weights: dict | None = None,
) -> dict:
    if not course_code or not course_code.strip():
        raise ManualCourseServiceError("Course code is required")
    if not course_name or not course_name.strip():
        raise ManualCourseServiceError("Course name is required")

    row = {
        "user_id": user_id,
        "course_code": course_code.strip(),
        "course_name": course_name.strip(),
        "term": (term or "").strip(),
        "weights": weights or {},
    }
    try:
        response = (
            _get_supabase_client()
            .table("manual_courses")
            .insert(row)
            .execute()
        )
    except Exception as exc:
        raise ManualCourseServiceError("Failed to create manual course") from exc
    if not response.data:
        raise ManualCourseServiceError("Failed to create manual course — no data returned")
    return _row_to_course(response.data[0])


def list_manual_courses(user_id: str) -> list[dict]:
    try:
        response = (
            _get_supabase_client()
            .table("manual_courses")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .execute()
        )
    except Exception as exc:
        raise ManualCourseServiceError("Failed to list manual courses") from exc
    return [_row_to_course(row) for row in (response.data or [])]


def get_manual_course(user_id: str, course_id: int) -> dict | None:
    try:
        response = (
            _get_supabase_client()
            .table("manual_courses")
            .select("*")
            .eq("user_id", user_id)
            .eq("id", course_id)
            .execute()
        )
    except Exception as exc:
        raise ManualCourseServiceError("Failed to get manual course") from exc
    if not response.data:
        return None
    return _row_to_course(response.data[0])


def update_manual_course(user_id: str, course_id: int, updates: dict) -> dict:
    allowed = {"course_code", "course_name", "term", "weights", "syllabus_source"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        raise ManualCourseServiceError("No valid fields to update")

    filtered["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        response = (
            _get_supabase_client()
            .table("manual_courses")
            .update(filtered)
            .eq("user_id", user_id)
            .eq("id", course_id)
            .execute()
        )
    except Exception as exc:
        raise ManualCourseServiceError("Failed to update manual course") from exc
    if not response.data:
        raise ManualCourseServiceError("Manual course not found")
    return _row_to_course(response.data[0])


def delete_manual_course(user_id: str, course_id: int) -> None:
    try:
        _get_supabase_client() \
            .table("manual_courses") \
            .delete() \
            .eq("user_id", user_id) \
            .eq("id", course_id) \
            .execute()
    except Exception as exc:
        raise ManualCourseServiceError("Failed to delete manual course") from exc


# ---------------------------------------------------------------------------
# Deadlines
# ---------------------------------------------------------------------------

def create_manual_deadline(
    user_id: str,
    course_id: int | None,
    course_code: str,
    name: str,
    due_at: str,
) -> dict:
    if not name or not name.strip():
        raise ManualCourseServiceError("Deadline name is required")
    if not due_at:
        raise ManualCourseServiceError("Due date is required")

    row: dict = {
        "user_id": user_id,
        "course_code": (course_code or "").strip(),
        "name": name.strip(),
        "due_at": due_at,
    }
    if course_id is not None:
        row["course_id"] = course_id

    try:
        response = (
            _get_supabase_client()
            .table("manual_deadlines")
            .insert(row)
            .execute()
        )
    except Exception as exc:
        raise ManualCourseServiceError("Failed to create deadline") from exc
    if not response.data:
        raise ManualCourseServiceError("Failed to create deadline — no data returned")
    return _row_to_deadline(response.data[0])


def list_manual_deadlines(user_id: str) -> list[dict]:
    try:
        response = (
            _get_supabase_client()
            .table("manual_deadlines")
            .select("*")
            .eq("user_id", user_id)
            .order("due_at", desc=False)
            .execute()
        )
    except Exception as exc:
        raise ManualCourseServiceError("Failed to list deadlines") from exc
    return [_row_to_deadline(row) for row in (response.data or [])]


def delete_manual_deadline(user_id: str, deadline_id: int) -> None:
    try:
        _get_supabase_client() \
            .table("manual_deadlines") \
            .delete() \
            .eq("user_id", user_id) \
            .eq("id", deadline_id) \
            .execute()
    except Exception as exc:
        raise ManualCourseServiceError("Failed to delete deadline") from exc
