from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

from api.services.course_service import get_dashboard_course, list_current_term_courses

_TTL = timedelta(minutes=5)
_CACHE: dict[str, dict[str, Any]] = {}
_LOCK = Lock()


def _is_fresh(entry: dict[str, Any] | None) -> bool:
    if not entry:
        return False
    cached_at = entry.get("cached_at")
    if not isinstance(cached_at, datetime):
        return False
    return datetime.now(timezone.utc) - cached_at < _TTL


def invalidate_grade_snapshot(user_id: str | int) -> None:
    with _LOCK:
        _CACHE.pop(str(user_id), None)


def get_grade_snapshot(user_id: str | int, quercus_token: str, force_refresh: bool = False) -> dict[str, Any]:
    cache_key = str(user_id)

    with _LOCK:
        entry = _CACHE.get(cache_key)
        if not force_refresh and _is_fresh(entry):
            return entry["data"]

    courses = list_current_term_courses(quercus_token)
    grade_rows = []
    errors = []

    for course in courses:
        try:
            dashboard_course = get_dashboard_course(quercus_token, course)
            grade_rows.append({
                "course_id": dashboard_course["id"],
                "course_name": dashboard_course["name"],
                "course_code": dashboard_course.get("course_code"),
                "current_grade": dashboard_course["current_grade"],
                "letter": dashboard_course["letter_grade"],
                "graded_weight": dashboard_course["progress_pct"],
            })
        except Exception as exc:
            errors.append({
                "course_id": course["id"],
                "course_name": course["name"],
                "course_code": course.get("course_code"),
                "error": str(exc),
            })

    data = {
        "courses": grade_rows,
        "errors": errors,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }

    with _LOCK:
        _CACHE[cache_key] = {
            "cached_at": datetime.now(timezone.utc),
            "data": data,
        }

    return data
