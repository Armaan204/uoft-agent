"""
api/services/acorn_service.py - ACORN import storage logic for FastAPI routes.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

from auth.user_store import get_supabase_client
from integrations.acorn_store import AcornStoreError, validate_payload

load_dotenv()


class AcornServiceError(RuntimeError):
    """Raised when the ACORN storage layer is misconfigured or fails."""


UNEARNED_GRADES = {"IPR", "NGA", "LWD"}


def _get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise AcornServiceError("SUPABASE_URL and SUPABASE_KEY must be configured")
    return create_client(url, key)


def import_acorn_data(import_code: str, data: dict[str, Any]) -> dict:
    """Validate and persist one ACORN import payload to Supabase."""
    payload = dict(data or {})
    payload["importCode"] = import_code
    validated = validate_payload(payload)
    row = {
        "import_code": validated["importCode"],
        "user_id": None,
        "data": validated,
        "imported_at": validated["importedAt"],
    }
    try:
        response = _get_supabase().table("acorn_imports").insert(row).execute()
    except Exception as exc:
        raise AcornServiceError("Failed to store ACORN import") from exc

    rows = getattr(response, "data", None) or []
    if not rows:
        raise AcornServiceError("Supabase returned no inserted ACORN import row")
    return validated


def get_latest_import(import_code: str) -> dict | None:
    """Return the latest ACORN import payload for one import code, or None."""
    normalized = validate_payload({"importCode": import_code, "courses": []})["importCode"]
    try:
        response = (
            _get_supabase()
            .table("acorn_imports")
            .select("data")
            .eq("import_code", normalized)
            .order("imported_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise AcornServiceError("Failed to load latest ACORN import") from exc

    rows = getattr(response, "data", None) or []
    if not rows:
        return None
    return rows[0].get("data")


def get_import_status(import_code: str) -> dict:
    """Return whether imported ACORN data exists for one import code."""
    normalized = validate_payload({"importCode": import_code, "courses": []})["importCode"]
    try:
        response = (
            _get_supabase()
            .table("acorn_imports")
            .select("data")
            .eq("import_code", normalized)
            .order("imported_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise AcornServiceError("Failed to load ACORN import status") from exc

    rows = getattr(response, "data", None) or []
    if not rows:
        return {"exists": False, "importedAt": None, "importCode": normalized}

    latest = rows[0].get("data") or {}
    return {
        "exists": True,
        "importedAt": latest.get("importedAt"),
        "importCode": latest.get("importCode", normalized),
        "courseCount": len(latest.get("courses", [])),
    }


def get_latest_import_for_user(user_id: str | int) -> dict | None:
    """Return the latest claimed ACORN import row for one user."""
    if user_id in (None, ""):
        return None

    try:
        response = (
            get_supabase_client()
            .table("acorn_imports")
            .select("id, data, imported_at")
            .eq("user_id", user_id)
            .order("imported_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise AcornServiceError("Failed to load saved ACORN import") from exc

    rows = getattr(response, "data", None) or []
    if not rows:
        return None

    row = rows[0]
    data = dict(row.get("data") or {})
    if row.get("imported_at") and not data.get("importedAt"):
        data["importedAt"] = row["imported_at"]
    return data


def _parse_credits(value: Any) -> float | None:
    try:
        credits = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if credits is None or credits <= 0:
        return None
    return credits


def _parse_mark(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _is_earned_course(course: dict[str, Any]) -> bool:
    grade = str(course.get("grade") or "").strip().upper()
    if grade in UNEARNED_GRADES or grade == "F":
        return False

    mark = _parse_mark(course.get("mark"))
    if mark is not None and mark < 50:
        return False

    return _parse_credits(course.get("credits")) is not None


def _should_deduplicate_course_code(course_code: str) -> bool:
    return bool(course_code) and "***" not in course_code


def _calculate_earned_credits(courses: list[dict[str, Any]]) -> float:
    credits_by_course_code: dict[str, float] = {}
    total_credits = 0.0

    for course in courses:
        course_code = str(course.get("courseCode") or course.get("code") or "").strip().upper()
        if not course_code or not _is_earned_course(course):
            continue

        credits = _parse_credits(course.get("credits"))
        if credits is None:
            continue

        if not _should_deduplicate_course_code(course_code):
            total_credits += credits
            continue

        current = credits_by_course_code.get(course_code, 0.0)
        if credits > current:
            credits_by_course_code[course_code] = credits

    return round(total_credits + sum(credits_by_course_code.values()), 2)


def get_academic_history(user_id: str | int) -> dict[str, Any]:
    """Return structured academic history for one user from the latest claimed ACORN import."""
    latest = get_latest_import_for_user(user_id)
    if not latest:
        return {"terms": [], "credits_earned": 0.0}

    raw_terms = latest.get("terms") or []
    structured_terms = []
    all_courses: list[dict[str, Any]] = []

    for term in raw_terms:
        courses = []
        for course in term.get("courses") or []:
            credits_raw = course.get("credits")

            courses.append({
                "code": course.get("courseCode"),
                "title": course.get("title"),
                "credits": credits_raw,
                "grade": course.get("grade"),
                "mark": course.get("mark"),
            })
            all_courses.append(course)

        structured_terms.append({
            "term": term.get("term"),
            "sessional_gpa": term.get("sessionalGpa"),
            "cumulative_gpa": term.get("cumulativeGpa"),
            "courses": courses,
        })

    return {
        "terms": structured_terms,
        "credits_earned": _calculate_earned_credits(all_courses),
        "imported_at": latest.get("importedAt"),
    }


def claim_latest_import_for_user(import_code: str, user_id: str | int) -> dict | None:
    """Attach the newest import for one import code to the given user account."""
    if not import_code or not str(import_code).strip():
        raise AcornStoreError("import_code must be provided")
    if user_id in (None, ""):
        raise AcornStoreError("user_id must be provided")

    normalized = validate_payload({"importCode": import_code, "courses": []})["importCode"]
    client = get_supabase_client()

    try:
        lookup = (
            client
            .table("acorn_imports")
            .select("id, data, imported_at")
            .eq("import_code", normalized)
            .order("imported_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise AcornServiceError("Failed to load ACORN import to claim") from exc

    rows = getattr(lookup, "data", None) or []
    if not rows:
        return None

    row = rows[0]
    try:
        (
            client
            .table("acorn_imports")
            .update({"user_id": user_id})
            .eq("id", row["id"])
            .execute()
        )
    except Exception as exc:
        raise AcornServiceError("Failed to claim ACORN import for user") from exc

    data = dict(row.get("data") or {})
    if row.get("imported_at") and not data.get("importedAt"):
        data["importedAt"] = row["imported_at"]
    return data
