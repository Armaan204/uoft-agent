from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from auth.user_store import UserStoreError, get_supabase_client


class GradesSnapshotServiceError(RuntimeError):
    """Raised when the grade snapshot persistence layer fails."""


def save_snapshot(
    user_id: str | int,
    courses_with_grades: list[dict[str, Any]],
    announcements: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Upsert one snapshot row per course for the given user."""
    if user_id in (None, ""):
        raise GradesSnapshotServiceError("user_id must be provided")

    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for course in courses_with_grades or []:
        course_id = course.get("course_id", course.get("id"))
        if course_id is None:
            continue

        row: dict[str, Any] = {
            "user_id": user_id,
            "course_id": int(course_id),
            "course_code": course.get("course_code") or course.get("courseCode") or "",
            "course_name": course.get("course_name") or course.get("name") or "",
            "current_grade": course.get("current_grade"),
            "letter_grade": course.get("letter_grade", course.get("letter")),
            "components": course.get("components"),
            "weights_source": course.get("weights_source"),
            "dashboard_data": course,
            "fetched_at": fetched_at,
        }
        if announcements is not None:
            row["announcements"] = announcements
        rows.append(row)

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


def get_dashboard_snapshot(user_id: str | int, max_age_minutes: int = 15) -> dict[str, Any] | None:
    """Return cached dashboard courses if the snapshot is younger than max_age_minutes, else None."""
    if user_id in (None, ""):
        return None

    try:
        response = (
            get_supabase_client()
            .table("grades_snapshot")
            .select("dashboard_data, fetched_at, announcements")
            .eq("user_id", user_id)
            .order("course_code")
            .execute()
        )
    except (UserStoreError, Exception) as exc:
        raise GradesSnapshotServiceError("Failed to load dashboard snapshot") from exc

    rows = getattr(response, "data", None) or []
    if not rows:
        return None

    fetched_values = [row.get("fetched_at") for row in rows if row.get("fetched_at")]
    if not fetched_values:
        return None

    try:
        newest = max(datetime.fromisoformat(str(v).replace("Z", "+00:00")) for v in fetched_values)
    except ValueError:
        return None

    if datetime.now(timezone.utc) - newest > timedelta(minutes=max_age_minutes):
        return None

    courses = [row["dashboard_data"] for row in rows if row.get("dashboard_data")]
    if not courses:
        return None

    announcements: list = []
    for row in rows:
        if row.get("announcements") is not None:
            announcements = row["announcements"]
            break

    term_name = next((c.get("term_name") for c in courses if c.get("term_name")), "")
    return {"courses": courses, "announcements": announcements, "term_name": term_name, "fetched_at": newest.isoformat()}


def save_course_detail_snapshot(user_id: str | int, course_id: int | str, data: dict[str, Any]) -> None:
    """Upsert course detail data into the matching grades_snapshot row."""
    if user_id in (None, ""):
        raise GradesSnapshotServiceError("user_id must be provided")

    cached_at = datetime.now(timezone.utc).isoformat()
    payload = {**data, "_cached_at": cached_at}

    try:
        (
            get_supabase_client()
            .table("grades_snapshot")
            .upsert(
                {
                    "user_id": user_id,
                    "course_id": int(course_id),
                    "course_detail_data": payload,
                },
                on_conflict="user_id,course_id",
            )
            .execute()
        )
    except (UserStoreError, Exception) as exc:
        raise GradesSnapshotServiceError("Failed to save course detail snapshot") from exc


def get_course_detail_snapshot(
    user_id: str | int,
    course_id: int | str,
    max_age_minutes: int = 60 * 24,
) -> dict[str, Any] | None:
    """Return cached course detail data if it exists and is fresh enough, else None."""
    if user_id in (None, ""):
        return None

    try:
        response = (
            get_supabase_client()
            .table("grades_snapshot")
            .select("course_detail_data")
            .eq("user_id", user_id)
            .eq("course_id", int(course_id))
            .execute()
        )
    except (UserStoreError, Exception) as exc:
        raise GradesSnapshotServiceError("Failed to load course detail snapshot") from exc

    rows = getattr(response, "data", None) or []
    if not rows or not rows[0].get("course_detail_data"):
        return None

    cached = rows[0]["course_detail_data"]
    cached_at = cached.get("_cached_at")
    if cached_at:
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(str(cached_at).replace("Z", "+00:00"))
            if age > timedelta(minutes=max_age_minutes):
                return None
        except ValueError:
            return None

    return {k: v for k, v in cached.items() if k != "_cached_at"}


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
