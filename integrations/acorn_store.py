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

    courses = payload.get("courses")
    if not isinstance(courses, list):
        raise AcornStoreError("Payload must include a 'courses' list")

    import_code = payload.get("importCode")
    if not isinstance(import_code, str) or not import_code.strip():
        raise AcornStoreError("Payload must include a non-empty importCode")
    import_code = _normalise_import_code(import_code)

    normalised_courses = []
    for i, course in enumerate(courses):
        if not isinstance(course, dict):
            raise AcornStoreError(f"Course at index {i} must be an object")
        course_code = course.get("courseCode")
        if not isinstance(course_code, str) or not course_code.strip():
            raise AcornStoreError(f"Course at index {i} is missing a valid courseCode")

        normalised_courses.append({
            "courseCode": course_code.strip(),
            "title": _clean_optional_str(course.get("title")),
            "term": _clean_optional_str(course.get("term")),
            "grade": _clean_optional_str(course.get("grade")),
            "mark": _clean_optional_str(course.get("mark")),
            "credits": _clean_optional_str(course.get("credits")),
            "rawText": _clean_optional_str(course.get("rawText")),
        })

    imported_at = payload.get("importedAt") or payload.get("capturedAt") or payload.get("extractedAt")
    if not isinstance(imported_at, str) or not imported_at.strip():
        imported_at = datetime.now(timezone.utc).isoformat()

    return {
        "importCode": import_code,
        "importedAt": imported_at,
        "source": _clean_optional_str(payload.get("source")),
        "sourceUrl": _clean_optional_str(payload.get("sourceUrl")),
        "courses": normalised_courses,
    }


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
