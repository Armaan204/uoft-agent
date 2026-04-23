"""
api/services/course_service.py - Uncached Quercus and grading service wrappers.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any

from bs4 import BeautifulSoup
from auth.user_store import UserStoreError, get_quercus_token
from calculator.grades import GradeCalculator, UOFT_THRESHOLDS
from integrations.quercus import QuercusClient, QuercusError
from integrations.syllabus import (
    SyllabusError,
    _ask_claude,
    _download_pdf,
    _extract_text,
    _extract_text_from_html,
    _load_persisted_weights,
    _save_persisted_weights,
    find_syllabus_file,
    find_syllabus_frontpage,
    find_syllabus_page,
)

_calc = GradeCalculator()


class CourseServiceError(RuntimeError):
    """Raised when the course API cannot resolve user or Quercus data."""


class UncachedQuercusClient(QuercusClient):
    """Quercus client variant that avoids Streamlit cache decorators."""

    def get_submissions(self, course_id: int | str) -> list:
        return self._get(
            f"/courses/{course_id}/students/submissions",
            params={"student_ids[]": "self"},
        )

    def get_assignment_groups(self, course_id: int | str) -> list:
        return self._get(
            f"/courses/{course_id}/assignment_groups",
            params={"include[]": "assignments"},
        )


def get_user_quercus_token(user_id: str | int) -> str:
    try:
        token = get_quercus_token(user_id)
    except UserStoreError as exc:
        raise CourseServiceError(str(exc)) from exc
    if not token:
        raise CourseServiceError("No saved Quercus token found for this user")
    return token


def list_current_term_courses(quercus_token: str) -> list[dict[str, Any]]:
    client = UncachedQuercusClient(token=quercus_token)
    courses = client.get_courses()
    return [
        {
            "id": course["id"],
            "name": course["name"],
            "course_code": course.get("course_code"),
            "term": course.get("term"),
        }
        for course in courses
    ]


def get_dashboard_course(quercus_token: str, course: dict[str, Any]) -> dict[str, Any]:
    client = UncachedQuercusClient(token=quercus_token)
    course_id = course["id"]
    groups = client.get_assignment_groups(course_id)
    submissions = client.get_submissions(course_id)
    weights, _source = _resolve_course_weights_uncached(course_id, client)

    if weights:
        component_model = _calc.build_weighted_components(groups, submissions, weights)
        if component_model["reliable"]:
            grade = _grade_from_components(component_model["components"])
        else:
            grade = _grade_from_points(groups, submissions)
    else:
        grade = _grade_from_points(groups, submissions)

    upcoming_deadlines = _get_upcoming_deadlines(client, course_id, course.get("course_code"))
    current_grade = grade["weighted_grade"]
    return {
        "id": course_id,
        "course_code": course.get("course_code"),
        "name": course.get("name"),
        "current_grade": current_grade,
        "letter_grade": grade["letter"],
        "risk_flag": _risk_flag(current_grade, grade["letter"] != "N/A"),
        "progress_pct": round(grade.get("graded_weight", 0.0), 2),
        "deadlines": upcoming_deadlines,
    }


def get_dashboard_announcements(quercus_token: str, courses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    client = UncachedQuercusClient(token=quercus_token)
    course_lookup = {course["id"]: course for course in courses}
    raw_announcements = client.get_latest_announcements(list(course_lookup.keys()))
    announcements = []

    for announcement in raw_announcements:
        context_code = announcement.get("context_code", "")
        if not context_code.startswith("course_"):
            continue
        try:
            course_id = int(context_code.split("_", 1)[1])
        except ValueError:
            continue

        course = course_lookup.get(course_id)
        if course is None:
            continue

        posted_at = announcement.get("posted_at")
        try:
            posted_dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00")) if posted_at else None
        except ValueError:
            posted_dt = None

        announcements.append({
            "course_id": course_id,
            "course_code": course.get("course_code") or course.get("name"),
            "title": announcement.get("title") or "Untitled announcement",
            "preview": _announcement_preview(announcement.get("message")),
            "url": announcement.get("html_url") or announcement.get("url"),
            "posted_at": posted_dt.isoformat() if posted_dt else None,
        })

    announcements.sort(key=lambda item: item["posted_at"] or "", reverse=True)
    return announcements


def get_latest_course_announcement(quercus_token: str, course_id: int | str) -> dict[str, Any]:
    client = UncachedQuercusClient(token=quercus_token)
    raw_announcements = client.get_latest_announcements([course_id])

    for announcement in raw_announcements:
        context_code = announcement.get("context_code", "")
        if context_code != f"course_{course_id}":
            continue

        posted_at = announcement.get("posted_at")
        try:
            posted_dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00")) if posted_at else None
        except ValueError:
            posted_dt = None

        message_html = announcement.get("message") or ""
        return {
            "course_id": int(course_id),
            "title": announcement.get("title") or "Untitled announcement",
            "body_html": _sanitize_announcement_html(message_html),
            "body_text": _announcement_text(message_html),
            "url": announcement.get("html_url") or announcement.get("url"),
            "posted_at": posted_dt.isoformat() if posted_dt else None,
        }

    raise CourseServiceError("No recent announcement found for this course")


def get_course_weights(quercus_token: str, course_id: int | str) -> dict[str, Any]:
    client = UncachedQuercusClient(token=quercus_token)
    weights, source = _resolve_course_weights_uncached(course_id, client)
    return {
        "course_id": int(course_id),
        "weights_source": source,
        "weights": weights or {},
    }


def get_course_grades(quercus_token: str, course_id: int | str) -> dict[str, Any]:
    client = UncachedQuercusClient(token=quercus_token)
    groups = client.get_assignment_groups(course_id)
    submissions = client.get_submissions(course_id)
    weights, source = _resolve_course_weights_uncached(course_id, client)
    enrollment = client.get_grades(course_id)

    if weights:
        component_model = _calc.build_weighted_components(groups, submissions, weights)
        grade = _grade_from_components(component_model["components"])
    else:
        component_model = None
        grade = _calc.current_grade(groups, submissions, {}) if False else _grade_from_points(groups, submissions)

    return {
        "course_id": int(course_id),
        "weights_source": source,
        "weights": weights or {},
        "grade": grade,
        "components": component_model["components"] if component_model else [],
        "component_model": component_model,
        "enrollment": {
            "current_score": enrollment.get("current_score"),
            "current_grade": enrollment.get("current_grade"),
            "final_score": enrollment.get("final_score"),
            "final_grade": enrollment.get("final_grade"),
        },
    }


def get_course_scenarios(quercus_token: str, course_id: int | str) -> dict[str, Any]:
    client = UncachedQuercusClient(token=quercus_token)
    groups = client.get_assignment_groups(course_id)
    submissions = client.get_submissions(course_id)
    weights, source = _resolve_course_weights_uncached(course_id, client)
    if not weights:
        raise CourseServiceError("No Canvas weights or accessible syllabus weights found for this course")

    grade_result = _calc.current_grade(groups, submissions, weights)
    current_pct = grade_result["weighted_grade"]

    sub_by_id = {submission["assignment_id"]: submission for submission in submissions}
    weights_lower = {key.lower(): (key, value) for key, value in weights.items()}
    ungraded_groups = []

    for group in groups:
        scorable = [assignment for assignment in group.get("assignments", []) if assignment.get("points_possible", 0) > 0]
        no_assignments_posted = len(scorable) == 0
        has_unscored = any(
            sub_by_id.get(assignment["id"]) is None
            or sub_by_id[assignment["id"]].get("score") is None
            for assignment in scorable
        )
        if not (no_assignments_posted or has_unscored):
            continue

        name_lower = group["name"].lower()
        weight_key = None
        if name_lower in weights_lower:
            weight_key = weights_lower[name_lower][0]
        else:
            for key, (original, _value) in weights_lower.items():
                if key in name_lower:
                    weight_key = original
                    break

        if weight_key is None:
            candidates = sorted(
                [(key, original) for key, (original, _value) in weights_lower.items() if name_lower in key],
                key=lambda item: len(item[0]),
            )
            if candidates:
                weight_key = candidates[0][1]

        if weight_key:
            ungraded_groups.append((weights[weight_key], group["name"], weight_key))

    if not ungraded_groups:
        return {
            "course_id": int(course_id),
            "weights_source": source,
            "current_grade": current_pct,
            "error": "No ungraded assessments found",
            "scenarios": {},
        }

    ungraded_groups.sort(reverse=True)
    final_weight_pct, final_name, _weight_key = ungraded_groups[0]
    scenarios = _calc.grade_scenarios(current_pct, final_weight_pct / 100.0)
    return {
        "course_id": int(course_id),
        "weights_source": source,
        "current_grade": current_pct,
        "final_assessment": final_name,
        "final_weight_pct": final_weight_pct,
        "scenarios": {
            letter: {"status": result["status"], "needed": result["needed"]}
            for letter, result in scenarios.items()
        },
        "targets": [{"letter": letter, "threshold": threshold} for letter, threshold in UOFT_THRESHOLDS],
    }


def _resolve_course_weights_uncached(course_id: int | str, client: UncachedQuercusClient) -> tuple[dict[str, float] | None, str | None]:
    weights = client.get_canvas_weights(course_id)
    if weights:
        return weights, "canvas"

    try:
        syllabus = client.get_syllabus(course_id)
        source_ref, syllabus_weights = parse_syllabus_weights_uncached(
            course_id=course_id,
            client=client,
            pdf_url=syllabus["pdf_urls"][0] if syllabus["pdf_urls"] else None,
        )
        if syllabus_weights:
            return syllabus_weights, source_ref
    except SyllabusError:
        pass

    return None, None


def _risk_flag(pct: float, has_data: bool) -> str:
    if not has_data:
        return "No breakdown"
    if pct < 70:
        return "At risk"
    if pct < 85:
        return "On track"
    return "Safe"


def _get_upcoming_deadlines(
    client: UncachedQuercusClient,
    course_id: int | str,
    course_code: str | None,
    days: int = 14,
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)
    deadlines = []
    for assignment in client.get_assignments(course_id):
        due_raw = assignment.get("due_at")
        if not due_raw:
            continue
        due_dt = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
        if now <= due_dt <= cutoff:
            deadlines.append({
                "name": assignment.get("name"),
                "due_at": due_dt.isoformat(),
                "course_code": course_code,
                "url": assignment.get("html_url"),
            })
    deadlines.sort(key=lambda item: item["due_at"])
    return deadlines


def _announcement_preview(html: str | None, limit: int = 180) -> str:
    text = _announcement_text(html)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _announcement_text(html: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return " ".join(unescape(text).split())


def _sanitize_announcement_html(html: str | None) -> str:
    soup = BeautifulSoup(html or "", "html.parser")

    for tag in soup.find_all(["script", "style", "iframe", "object", "embed", "form", "input", "button"]):
        tag.decompose()

    for tag in soup.find_all(True):
        attrs_to_remove = []
        for attr_name, attr_value in list(tag.attrs.items()):
            if attr_name.lower().startswith("on"):
                attrs_to_remove.append(attr_name)
                continue
            if attr_name.lower() in {"href", "src"} and isinstance(attr_value, str) and attr_value.strip().lower().startswith("javascript:"):
                attrs_to_remove.append(attr_name)
        for attr_name in attrs_to_remove:
            tag.attrs.pop(attr_name, None)

    return str(soup)


def parse_syllabus_weights_uncached(
    course_id: int | str,
    client: UncachedQuercusClient,
    pdf_url: str | None = None,
) -> tuple[str, dict[str, float]]:
    """Mirror integrations.syllabus.parse_syllabus_weights without st.cache_data."""
    source_url = pdf_url

    if not source_url:
        source_url = find_syllabus_file(course_id, client)

    if not source_url:
        source_url = find_syllabus_frontpage(course_id, client)

    if not source_url:
        page_candidate = find_syllabus_page(course_id, client)
        if page_candidate:
            source_ref = f"canvas-page:{page_candidate['page_slug']}"
            cached = _load_persisted_weights(course_id, source_ref)
            if cached:
                return source_ref, cached
            page = client.get_page(course_id, page_candidate["page_slug"])
            text = _extract_text_from_html(page.get("body") or "")
            weights = _ask_claude(text)
            _save_persisted_weights(course_id, source_ref, weights)
            return source_ref, weights

    if not source_url:
        raise SyllabusError(
            f"No syllabus PDF found for course {course_id} "
            "(tried syllabus_body, files/modules/front page, and Canvas pages)"
        )

    cached = _load_persisted_weights(course_id, source_url)
    if cached:
        return source_url, cached

    pdf_bytes = _download_pdf(source_url)
    text = _extract_text(pdf_bytes)
    weights = _ask_claude(text)
    _save_persisted_weights(course_id, source_url, weights)
    return source_url, weights


def _grade_from_points(groups: list[dict[str, Any]], submissions: list[dict[str, Any]]) -> dict[str, Any]:
    sub_by_id = {submission["assignment_id"]: submission for submission in submissions}
    total_earned = 0.0
    total_possible = 0.0
    group_breakdown: dict[str, dict[str, Any]] = {}

    for group in groups:
        group_earned = 0.0
        group_possible = 0.0
        for assignment in group.get("assignments", []):
            submission = sub_by_id.get(assignment["id"])
            if submission is None or submission.get("score") is None:
                continue
            group_earned += submission["score"]
            group_possible += assignment.get("points_possible") or 0

        if group_possible == 0:
            continue

        group_name = group["name"]
        if group_name in group_breakdown:
            group_breakdown[group_name]["earned"] += group_earned
            group_breakdown[group_name]["possible"] += group_possible
            group_breakdown[group_name]["pct"] = round(
                group_breakdown[group_name]["earned"] / group_breakdown[group_name]["possible"] * 100,
                2,
            )
        else:
            group_breakdown[group_name] = {
                "earned": group_earned,
                "possible": group_possible,
                "pct": round(group_earned / group_possible * 100, 2),
            }

        total_earned += group_earned
        total_possible += group_possible

    if total_possible == 0:
        return {"weighted_grade": 0.0, "letter": "N/A", "gpa_points": None, "group_breakdown": {}, "graded_weight": 0.0}

    pct = total_earned / total_possible * 100
    return {
        "weighted_grade": round(pct, 2),
        "letter": _calc._to_letter(pct),
        "gpa_points": _calc._to_gpa_points(pct),
        "group_breakdown": group_breakdown,
        "graded_weight": 100.0,
        "_total_earned": total_earned,
        "_total_possible": total_possible,
    }


def _grade_from_components(components: list[dict[str, Any]]) -> dict[str, Any]:
    graded_components = [component for component in components if component["status"] == "graded"]
    graded_weight = sum(component["weight"] for component in graded_components)
    if graded_weight <= 0:
        return {
            "weighted_grade": 0.0,
            "letter": "N/A",
            "gpa_points": None,
            "group_breakdown": {},
            "graded_weight": 0.0,
        }

    weighted_sum = sum(component["pct"] * component["weight"] for component in graded_components)
    weighted_grade = weighted_sum / graded_weight
    return {
        "weighted_grade": round(weighted_grade, 2),
        "letter": _calc._to_letter(weighted_grade),
        "gpa_points": _calc._to_gpa_points(weighted_grade),
        "group_breakdown": {
            component["name"]: {
                "earned": component["earned"],
                "possible": component["possible"],
                "pct": component["pct"],
                "weight": component["weight"],
            }
            for component in graded_components
        },
        "graded_weight": round(graded_weight, 2),
    }
