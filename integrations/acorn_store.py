"""
integrations/acorn_store.py — file-backed storage for imported ACORN data.

The Chrome extension POSTs parsed academic-history payloads to the local API.
This module validates the basic shape and stores the latest payload for a
single import code in one JSON file on disk.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
IMPORTS_DIR = DATA_DIR / "acorn_imports"


class AcornStoreError(Exception):
    """Raised when ACORN payload validation or storage fails."""


def validate_payload(payload: object) -> dict:
    """Validate the minimal ACORN import shape expected from the extension."""
    if not isinstance(payload, dict):
        raise AcornStoreError("Payload must be a JSON object")

    import_code = payload.get("importCode")
    if not isinstance(import_code, str) or not import_code.strip():
        raise AcornStoreError("Payload must include a non-empty importCode")
    import_code = _normalise_import_code(import_code)

    # --- terms (new structured format) ---
    normalised_terms = None
    terms = payload.get("terms")
    if isinstance(terms, list):
        normalised_terms = []
        for i, term_obj in enumerate(terms):
            if not isinstance(term_obj, dict):
                raise AcornStoreError(f"Term at index {i} must be an object")
            term_name = _clean_optional_str(term_obj.get("term"))
            sessional_gpa = term_obj.get("sessionalGpa")
            cumulative_gpa = term_obj.get("cumulativeGpa")
            status = _clean_optional_str(term_obj.get("status"))

            term_courses_raw = term_obj.get("courses")
            term_courses = []
            if isinstance(term_courses_raw, list):
                for j, course in enumerate(term_courses_raw):
                    if not isinstance(course, dict):
                        raise AcornStoreError(f"Course at term {i}, index {j} must be an object")
                    course_code = course.get("courseCode")
                    if not isinstance(course_code, str) or not course_code.strip():
                        raise AcornStoreError(
                            f"Course at term {i}, index {j} is missing a valid courseCode"
                        )
                    term_courses.append(_normalise_course(course, term_name))

            normalised_terms.append({
                "term": term_name,
                "sessionalGpa": sessional_gpa if isinstance(sessional_gpa, (int, float)) else None,
                "cumulativeGpa": cumulative_gpa if isinstance(cumulative_gpa, (int, float)) else None,
                "status": status,
                "courses": term_courses,
            })

    # --- courses (flat list) ---
    if normalised_terms is not None:
        # Derive the flat list from terms so both representations stay in sync.
        normalised_courses = [c for t in normalised_terms for c in t["courses"]]
    else:
        # Legacy format: flat courses list with no terms.
        courses = payload.get("courses")
        if not isinstance(courses, list):
            raise AcornStoreError("Payload must include a 'courses' list or 'terms' array")
        normalised_courses = []
        for i, course in enumerate(courses):
            if not isinstance(course, dict):
                raise AcornStoreError(f"Course at index {i} must be an object")
            course_code = course.get("courseCode")
            if not isinstance(course_code, str) or not course_code.strip():
                raise AcornStoreError(f"Course at index {i} is missing a valid courseCode")
            normalised_courses.append(_normalise_course(course, None))

    imported_at = payload.get("importedAt") or payload.get("capturedAt") or payload.get("extractedAt")
    if not isinstance(imported_at, str) or not imported_at.strip():
        imported_at = datetime.now(timezone.utc).isoformat()

    result = {
        "importCode": import_code,
        "importedAt": imported_at,
        "source": _clean_optional_str(payload.get("source")),
        "sourceUrl": _clean_optional_str(payload.get("sourceUrl")),
        "courses": normalised_courses,
    }
    if normalised_terms is not None:
        result["terms"] = normalised_terms
    return result


def write_latest(payload: dict) -> dict:
    """Persist the latest ACORN payload for its import code and return it."""
    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    validated = validate_payload(payload)
    _path_for_code(validated["importCode"]).write_text(json.dumps(validated, indent=2), encoding="utf-8")
    return validated


def read_latest(import_code: str) -> dict | None:
    """Return the latest ACORN payload for one import code, or None."""
    path = _path_for_code(import_code)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def get_status(import_code: str) -> dict:
    """Return whether imported ACORN data exists for one import code."""
    latest = read_latest(import_code)
    if latest is None:
        return {"exists": False, "importedAt": None, "importCode": _normalise_import_code(import_code)}
    return {
        "exists": True,
        "importedAt": latest.get("importedAt"),
        "importCode": latest.get("importCode"),
        "courseCount": len(latest.get("courses", [])),
    }


def _normalise_course(course: dict, term: str | None) -> dict:
    return {
        "courseCode": course["courseCode"].strip(),
        "title": _clean_optional_str(course.get("title")),
        "term": _clean_optional_str(course.get("term")) or term,
        "grade": _clean_optional_str(course.get("grade")),
        "mark": _clean_optional_str(course.get("mark")),
        "credits": _clean_optional_str(course.get("credits")),
        "courseAverage": _clean_optional_str(course.get("courseAverage")),
        "rawText": _clean_optional_str(course.get("rawText")),
    }


def _path_for_code(import_code: str) -> Path:
    return IMPORTS_DIR / f"{_normalise_import_code(import_code)}.json"


def _normalise_import_code(value: str) -> str:
    cleaned = "".join(ch for ch in value.upper().strip() if ch.isalnum())
    if not cleaned:
        raise AcornStoreError("importCode must contain letters or numbers")
    return cleaned


def _clean_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    cleaned = value.strip()
    return cleaned or None
