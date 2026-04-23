from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from auth.user_store import UserStoreError, get_supabase_client


class GradesSnapshotServiceError(RuntimeError):
    """Raised when the grade snapshot persistence layer fails."""


def save_snapshot(user_id: str | int, courses_with_grades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Upsert one snapshot row per course for the given user."""
    if user_id in (None, ""):
        raise GradesSnapshotServiceError("user_id must be provided")

    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for course in courses_with_grades or []:
        course_id = course.get("course_id", course.get("id"))
        if course_id is None:
            continue

        rows.append({
            "user_id": user_id,
            "course_id": int(course_id),
            "course_code": course.get("course_code") or course.get("courseCode") or "",
            "course_name": course.get("course_name") or course.get("name") or "",
            "current_grade": course.get("current_grade"),
            "letter_grade": course.get("letter_grade", course.get("letter")),
            "components": course.get("components"),
            "weights_source": course.get("weights_source"),
            "fetched_at": fetched_at,
        })

    if not rows:
        return []

    try:
        response = (
            get_supabase_client()
            .table("grades_snapshot")
            .upsert(rows, on_conflict="user_id,course_id")
            .execute()
        )
    except (UserStoreError, Exception) as exc:
        raise GradesSnapshotServiceError("Failed to save grade snapshot") from exc

    return getattr(response, "data", None) or rows


def get_snapshot(user_id: str | int) -> list[dict[str, Any]]:
    """Return all persisted grade snapshot rows for one user."""
    if user_id in (None, ""):
        return []

    try:
        response = (
            get_supabase_client()
            .table("grades_snapshot")
            .select("*")
            .eq("user_id", user_id)
            .order("course_code")
            .execute()
        )
    except (UserStoreError, Exception) as exc:
        raise GradesSnapshotServiceError("Failed to load grade snapshot") from exc

    return getattr(response, "data", None) or []


def is_snapshot_stale(user_id: str | int, max_age_minutes: int = 5) -> bool:
    """Return True when no snapshot exists or when its newest row is too old."""
    rows = get_snapshot(user_id)
    if not rows:
        return True

    fetched_values = [row.get("fetched_at") for row in rows if row.get("fetched_at")]
    if not fetched_values:
        return True

    try:
        newest = max(datetime.fromisoformat(str(value).replace("Z", "+00:00")) for value in fetched_values)
    except ValueError:
        return True

    return datetime.now(timezone.utc) - newest > timedelta(minutes=max_age_minutes)
