"""
agent/tools.py — Claude tool definitions (JSON schemas) and dispatch.

TOOL_SCHEMAS  : list passed directly to the Anthropic messages API.
execute_tool  : called by the agent loop; accepts a QuercusClient so the
                token flows in from session state rather than from .env.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from html import unescape

from api.services.acorn_service import get_academic_history as load_academic_history
from api.services.grade_snapshot_cache import get_grade_snapshot, invalidate_grade_snapshot
from api.services.grades_snapshot_service import get_snapshot as load_grades_snapshot, save_snapshot
from api.services.manual_course_service import (
    ManualCourseServiceError,
    list_manual_courses,
    list_manual_deadlines,
    get_manual_course,
)
from api.integrations.grades_cache import get_grade_overrides
from api.integrations.graduation_service import check_graduation_progress as _check_grad_progress
from api.integrations.graduation_service import get_program_requirements as _get_prog_reqs
from api.integrations.quercus import QuercusClient
from api.integrations.syllabus import parse_syllabus_weights
from api.calculator.grades import GradeCalculator

logger = logging.getLogger(__name__)

_calc = GradeCalculator()


def _has_token(client: QuercusClient) -> bool:
    return bool(getattr(client, "_token", None))


def _manual_course_summaries(user_id: str | int) -> list[dict]:
    try:
        courses = list_manual_courses(str(user_id))
    except ManualCourseServiceError:
        return []
    results = []
    for c in courses:
        try:
            overrides = get_grade_overrides(str(user_id), c["id"])
        except Exception:
            overrides = {}
        weights = c.get("weights") or {}
        grade_info = _compute_manual_grade(weights, overrides)
        results.append({
            "course_id": c["id"],
            "course_name": c["course_name"],
            "course_code": c["course_code"],
            "source": "manual",
            **grade_info,
        })
    return results


def _compute_manual_grade(weights: dict, overrides: dict) -> dict:
    components = []
    for name, weight in weights.items():
        override = overrides.get(name)
        if override is not None:
            score = float(override.get("manual_score", 0))
            possible = float(override.get("manual_possible", 100))
            pct = (score / possible * 100) if possible > 0 else 0.0
            components.append({"name": name, "weight": float(weight), "pct": pct, "graded": True})
        else:
            components.append({"name": name, "weight": float(weight), "pct": None, "graded": False})

    total_weight = sum(c["weight"] for c in components)
    graded_weight = sum(c["weight"] for c in components if c["graded"])

    if total_weight > 0:
        projected_sum = sum((c["pct"] if c["graded"] else 100) * c["weight"] for c in components)
        current_grade = round(projected_sum / total_weight, 2)
        letter = GradeCalculator._to_letter(current_grade)
    else:
        current_grade = 0.0
        letter = "N/A"

    return {
        "current_grade": current_grade,
        "letter": letter,
        "gpa_points": GradeCalculator._to_gpa_points(current_grade) if letter != "N/A" else None,
        "graded_weight": graded_weight,
    }


# ---------------------------------------------------------------------------
# JSON schemas — passed to Claude as the `tools` parameter
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "name": "get_courses",
        "description": (
            "Return the list of courses the student is currently enrolled in. "
            "Call this first when the student asks about a course by name but "
            "you need to resolve it to a course_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_all_grades",
        "description": (
            "Return the student's current grade across all current courses in one call. "
            "Use this for multi-course questions like GPA tracking, comparing courses, "
            "or listing current grades across the semester."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_academic_history",
        "description": (
            "Return the student's saved ACORN academic history, including course history, "
            "credits earned, and GPA by term. Each course includes the student's own mark and grade, "
            "plus a course_average field which is the class-wide average (how the course performed overall), "
            "not the student's personal score. The response also includes a courses_by_mark list — all graded "
            "courses sorted ascending by numerical mark (lowest = worst at index 0, highest = best at end). "
            "Use courses_by_mark for best/worst/ranking questions instead of sorting yourself. "
            "Prefer this for past performance and GPA history questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_cached_grades",
        "description": (
            "Return the student's persisted current-grade snapshot from Supabase. "
            "Prefer this for current-grade questions because it is much faster than live Quercus fetches. "
            "The snapshot is refreshed when the dashboard loads or when refresh_grades is called."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "refresh_grades",
        "description": (
            "Fetch fresh current grades from Quercus across all current courses, save them to the persisted "
            "grades snapshot, and return the updated results. Use this only when the user explicitly asks for "
            "updated, refreshed, or latest current grade data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_all_announcements",
        "description": (
            "Return the most recent announcement from every course in one call. "
            "Use this when the user asks to summarize, list, or check announcements "
            "across multiple courses or without specifying a course. "
            "Reads from the cached snapshot when available (zero API calls); "
            "falls back to a single Quercus request for all courses."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_course_announcements",
        "description": (
            "Return up to 10 recent announcements for one specific course as lightweight previews. "
            "Only use this when the user asks about announcements for a particular course "
            "and needs more than just the latest one. Prefer get_all_announcements for "
            "general or multi-course announcement questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "Canvas course ID"},
                "course_name": {"type": "string", "description": "Human-readable course name for context"},
            },
            "required": ["course_id", "course_name"],
        },
    },
    {
        "name": "get_announcement_detail",
        "description": (
            "Return the full content for a single announcement. Use only when the user explicitly asks "
            "to read one announcement in detail."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "Canvas course ID"},
                "announcement_id": {"type": "integer", "description": "Canvas announcement ID"},
            },
            "required": ["course_id", "announcement_id"],
        },
    },
    {
        "name": "get_course_weights",
        "description": (
            "Fetch the grade breakdown (assessment categories and their percentage "
            "weights) for a course. Uses Canvas group weights when configured; "
            "falls back to syllabus PDF parsing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "course_id":   {"type": "integer", "description": "Canvas course ID"},
                "course_name": {"type": "string",  "description": "Human-readable course name for context"},
            },
            "required": ["course_id", "course_name"],
        },
    },
    {
        "name": "get_current_grade",
        "description": (
            "Compute the student's current weighted grade in a course based on "
            "graded submissions so far. Returns overall percentage, UofT letter grade, "
            "UofT GPA points, and a per-group breakdown."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "course_id":   {"type": "integer", "description": "Canvas course ID"},
                "course_name": {"type": "string",  "description": "Human-readable course name for context"},
            },
            "required": ["course_id", "course_name"],
        },
    },
    {
        "name": "get_grade_scenarios",
        "description": (
            "For a course with an ungraded final assessment, compute what score "
            "the student needs on that assessment to achieve each UofT letter grade "
            "(A+ through F). Returns a dict of letter → required score."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "course_id":   {"type": "integer", "description": "Canvas course ID"},
                "course_name": {"type": "string",  "description": "Human-readable course name for context"},
            },
            "required": ["course_id", "course_name"],
        },
    },
    {
        "name": "get_upcoming_deadlines",
        "description": (
            "Return upcoming assignment due dates across all of the student's current courses. "
            "Use this when the student asks what is due soon, what their next deadline is, "
            "what assignments are coming up, or anything about upcoming due dates. "
            "Returns deadlines sorted by due date. Reads from the cached dashboard snapshot "
            "when available (fast); falls back to a live Quercus fetch otherwise."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "How many days ahead to look for deadlines (default 14, max 30).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "check_graduation_progress",
        "description": (
            "Check the student's graduation progress against their program requirements. "
            "Requires ACORN academic history to be imported. Returns a breakdown of each "
            "requirement group showing which requirements are satisfied, in-progress, or "
            "remaining, plus overall credits completed vs. required. "
            "Use this when the student asks about graduation, program completion, degree "
            "requirements, or how many credits they need to graduate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

# ---------------------------------------------------------------------------
# Tool implementations — each takes (inp, client)
# ---------------------------------------------------------------------------

def _get_courses(inp: dict, client: QuercusClient, user_id: str | int | None = None) -> list:
    quercus_courses = []
    if _has_token(client):
        try:
            quercus_courses = [
                {"id": c["id"], "name": c["name"], "course_code": c["course_code"], "source": "quercus"}
                for c in client.get_courses()
            ]
        except Exception:
            pass

    manual = []
    if user_id:
        try:
            manual = [
                {"id": c["id"], "name": c["course_name"], "course_code": c["course_code"], "source": "manual"}
                for c in list_manual_courses(str(user_id))
            ]
        except ManualCourseServiceError:
            pass

    return quercus_courses + manual


def _get_course_weights(inp: dict, client: QuercusClient, user_id: str | int | None = None) -> dict:
    course_id = inp["course_id"]

    if course_id < 0 and user_id:
        course = get_manual_course(str(user_id), course_id)
        if course:
            return course.get("weights") or {}
        return {"error": "Manual course not found"}

    # Preferred path: Canvas group_weight — no LLM or PDF needed
    canvas_weights = client.get_canvas_weights(course_id)
    if canvas_weights:
        return canvas_weights

    # Fallback: parse syllabus PDF
    syllabus = client.get_syllabus(course_id)
    pdf_url  = syllabus["pdf_urls"][0] if syllabus["pdf_urls"] else None
    _src, weights = parse_syllabus_weights(course_id, client, pdf_url)
    return weights


def _build_grade_summary(course: dict, client: QuercusClient) -> dict:
    inp = {
        "course_id": course["id"],
        "course_name": course["name"],
    }
    grade = _get_current_grade(inp, client)
    return {
        "course_id": course["id"],
        "course_name": course["name"],
        "course_code": course.get("course_code"),
        "current_grade": grade["weighted_grade"],
        "letter": grade["letter"],
        "gpa_points": grade["gpa_points"],
        "graded_weight": grade["graded_weight"],
    }


def _get_current_grade(inp: dict, client: QuercusClient, user_id: str | int | None = None) -> dict:
    course_id = inp["course_id"]

    if course_id < 0 and user_id:
        course = get_manual_course(str(user_id), course_id)
        if not course:
            return {"error": "Manual course not found"}
        weights = course.get("weights") or {}
        try:
            overrides = get_grade_overrides(str(user_id), course_id)
        except Exception:
            overrides = {}
        info = _compute_manual_grade(weights, overrides)
        return {
            "weighted_grade": info["current_grade"],
            "letter": info["letter"],
            "gpa_points": info["gpa_points"],
            "graded_weight": info["graded_weight"],
            "source": "manual",
        }

    groups      = client.get_assignment_groups(course_id)
    submissions = client.get_submissions(course_id)
    weights     = _get_course_weights(inp, client)
    return _calc.current_grade(groups, submissions, weights)


def _preview_text(html: str | None, limit: int = 100) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = " ".join(unescape(text).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _get_academic_history(inp: dict, client: QuercusClient, user_id: str | int | None = None) -> dict:
    if user_id is None:
        return {"error": "Academic history requires an authenticated user context"}
    return load_academic_history(user_id)


def _get_cached_grades(inp: dict, client: QuercusClient, user_id: str | int | None = None) -> dict:
    if user_id is None:
        return {"error": "Cached grades require an authenticated user context"}

    snapshot_rows = load_grades_snapshot(user_id)
    courses = [
        {
            "course_id": row["course_id"],
            "course_name": row.get("course_name"),
            "course_code": row.get("course_code"),
            "current_grade": row.get("current_grade"),
            "letter": row.get("letter_grade"),
            "graded_weight": None,
        }
        for row in snapshot_rows
    ] if snapshot_rows else []

    manual = _manual_course_summaries(user_id)
    courses += manual

    fetched_values = [row.get("fetched_at") for row in (snapshot_rows or []) if row.get("fetched_at")]
    fetched_at = max(fetched_values) if fetched_values else None

    return {
        "courses": courses,
        "errors": [],
        "fetched_at": fetched_at,
    }


def _get_all_grades(inp: dict, client: QuercusClient, user_id: str | int | None = None) -> dict:
    manual = _manual_course_summaries(user_id) if user_id else []

    if user_id is not None and _has_token(client):
        snapshot = get_grade_snapshot(user_id, client._token)
        snapshot["courses"] = snapshot.get("courses", []) + manual
        return snapshot

    if not _has_token(client):
        return {"courses": manual, "errors": []}

    courses = client.get_courses()
    grades = []
    errors = []

    for course in courses:
        try:
            grades.append(_build_grade_summary(course, client))
        except Exception as exc:
            errors.append({
                "course_id": course["id"],
                "course_name": course["name"],
                "course_code": course.get("course_code"),
                "error": str(exc),
            })

    return {
        "courses": grades + manual,
        "errors": errors,
    }


def _refresh_grades(inp: dict, client: QuercusClient, user_id: str | int | None = None) -> dict:
    manual = _manual_course_summaries(user_id) if user_id else []

    if user_id is None or not _has_token(client):
        return {"courses": manual, "errors": []}

    invalidate_grade_snapshot(user_id)
    fresh = get_grade_snapshot(user_id, client._token, force_refresh=True)
    save_snapshot(user_id, fresh.get("courses", []))
    fresh["courses"] = fresh.get("courses", []) + manual
    return fresh


def _get_all_announcements(inp: dict, client: QuercusClient, user_id: str | int | None = None) -> dict:
    # Fast path: read from dashboard snapshot (already aggregated, zero API calls)
    if user_id is not None:
        snapshot_rows = load_grades_snapshot(user_id)
        for row in snapshot_rows:
            if row.get("announcements") is not None:
                return {"announcements": row["announcements"], "source": "snapshot"}

    if not _has_token(client):
        return {"announcements": [], "source": "none", "note": "Announcements require a Quercus connection."}

    # Live path: one API call for all courses
    courses = client.get_courses()
    course_lookup = {c["id"]: c for c in courses}
    raw = client.get_latest_announcements(list(course_lookup.keys()))

    announcements = []
    for ann in raw:
        context_code = ann.get("context_code", "")
        if not context_code.startswith("course_"):
            continue
        try:
            course_id = int(context_code.split("_", 1)[1])
        except ValueError:
            continue
        course = course_lookup.get(course_id)
        posted_at = ann.get("posted_at")
        announcements.append({
            "course_id": course_id,
            "course_code": course.get("course_code") if course else None,
            "course_name": course.get("name") if course else None,
            "title": ann.get("title") or "Untitled announcement",
            "preview": _preview_text(ann.get("message"), limit=200),
            "url": ann.get("html_url") or ann.get("url"),
            "posted_at": posted_at,
        })

    announcements.sort(key=lambda a: a.get("posted_at") or "", reverse=True)
    return {"announcements": announcements, "source": "live"}


def _get_course_announcements(inp: dict, client: QuercusClient) -> dict:
    course_id = inp["course_id"]
    if course_id < 0 or not _has_token(client):
        return {"course_id": course_id, "announcements": [], "note": "Announcements require a Quercus connection."}
    announcements = client.get_course_announcements(course_id, limit=10)
    return {
        "course_id": course_id,
        "course_name": inp.get("course_name"),
        "announcements": [
            {
                "id": announcement.get("id"),
                "title": announcement.get("title") or "Untitled announcement",
                "posted_at": announcement.get("posted_at"),
                "preview": _preview_text(announcement.get("message"), limit=100),
            }
            for announcement in announcements
        ],
    }


def _get_announcement_detail(inp: dict, client: QuercusClient) -> dict:
    course_id = inp["course_id"]
    if course_id < 0 or not _has_token(client):
        return {"error": "Announcements require a Quercus connection."}
    announcement_id = inp["announcement_id"]
    announcement = client.get_announcement_detail(announcement_id)
    return {
        "course_id": course_id,
        "announcement_id": announcement_id,
        "title": announcement.get("title") or "Untitled announcement",
        "posted_at": announcement.get("posted_at"),
        "body": " ".join(unescape(re.sub(r"<[^>]+>", " ", announcement.get("message") or "")).split()),
        "url": announcement.get("html_url") or announcement.get("url"),
    }


def _get_upcoming_deadlines_tool(inp: dict, client: QuercusClient, user_id: str | int | None = None) -> dict:
    days = min(int(inp.get("days") or 14), 30)
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)
    deadlines: list[dict] = []

    # Include manual deadlines
    if user_id is not None:
        try:
            manual_dls = list_manual_deadlines(str(user_id))
            for dl in manual_dls:
                due_raw = dl.get("due_at")
                if not due_raw:
                    continue
                try:
                    due_dt = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if now <= due_dt <= cutoff:
                    deadlines.append({
                        "name": dl.get("name"),
                        "due_at": due_dt.isoformat(),
                        "course_code": dl.get("course_code", ""),
                        "course_name": None,
                        "url": None,
                        "source": "manual",
                    })
        except ManualCourseServiceError:
            pass

    # Fast path: read from cached dashboard snapshot (avoids Quercus API calls)
    if user_id is not None:
        snapshot_rows = load_grades_snapshot(user_id)
        if snapshot_rows:
            for row in snapshot_rows:
                dashboard_data = row.get("dashboard_data") or {}
                course_code = row.get("course_code") or dashboard_data.get("course_code")
                course_name = row.get("course_name") or dashboard_data.get("name")
                for dl in dashboard_data.get("deadlines") or []:
                    due_raw = dl.get("due_at")
                    if not due_raw:
                        continue
                    try:
                        due_dt = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    if now <= due_dt <= cutoff:
                        deadlines.append({
                            "name": dl.get("name"),
                            "due_at": due_dt.isoformat(),
                            "course_code": course_code,
                            "course_name": course_name,
                            "url": dl.get("url"),
                        })
            if deadlines or snapshot_rows:
                deadlines.sort(key=lambda d: d["due_at"])
                return {"deadlines": deadlines, "days": days, "source": "snapshot"}

    if not _has_token(client):
        deadlines.sort(key=lambda d: d["due_at"])
        return {"deadlines": deadlines, "days": days, "source": "manual_only"}

    # Live fetch fallback: query Quercus directly
    courses = client.get_courses()
    for course in courses:
        course_id = course["id"]
        try:
            for assignment in client.get_assignments(course_id):
                due_raw = assignment.get("due_at")
                if not due_raw:
                    continue
                try:
                    due_dt = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if now <= due_dt <= cutoff:
                    deadlines.append({
                        "name": assignment.get("name"),
                        "due_at": due_dt.isoformat(),
                        "course_code": course.get("course_code"),
                        "course_name": course.get("name"),
                        "url": assignment.get("html_url"),
                    })
        except Exception:
            pass

    deadlines.sort(key=lambda d: d["due_at"])
    return {"deadlines": deadlines, "days": days, "source": "live"}


def _check_graduation_progress(inp: dict, client: QuercusClient, user_id: str | int | None = None) -> dict:
    if user_id is None:
        return {"error": "Graduation progress requires an authenticated user context"}

    acorn_data = load_academic_history(user_id)
    programs = acorn_data.get("programs") or []
    if not programs:
        return {
            "error": "No ACORN data found. Please import your ACORN academic history "
                     "using the ACORN tab before checking graduation progress."
        }

    program_name = (programs[0].get("programName") or "").strip()
    if not program_name:
        return {"error": "Could not determine program name from ACORN data."}

    requirements = _get_prog_reqs(program_name)
    if requirements is None:
        return {
            "error": f"Could not find calendar requirements for: {program_name}. "
                     "The program may not be supported yet or the calendar page could not be reached."
        }

    return _check_grad_progress(requirements, acorn_data)


def _get_grade_scenarios(inp: dict, client: QuercusClient, user_id: str | int | None = None) -> dict:
    course_id = inp["course_id"]

    if course_id < 0 and user_id:
        course = get_manual_course(str(user_id), course_id)
        if not course:
            return {"error": "Manual course not found"}
        weights = course.get("weights") or {}
        if not weights:
            return {"error": "No weights defined for this manual course"}
        try:
            overrides = get_grade_overrides(str(user_id), course_id)
        except Exception:
            overrides = {}
        info = _compute_manual_grade(weights, overrides)
        graded_names = set(overrides.keys())
        ungraded = [(float(w), name) for name, w in weights.items() if name not in graded_names]
        if not ungraded:
            return {"error": "No ungraded assessments found"}
        ungraded.sort(reverse=True)
        final_weight_pct, final_name = ungraded[0]
        final_weight = final_weight_pct / 100.0
        scenarios = _calc.grade_scenarios(info["current_grade"], final_weight)
        return {
            "current_grade": info["current_grade"],
            "final_assessment": final_name,
            "final_weight_pct": final_weight_pct,
            "scenarios": {
                letter: {"status": r["status"], "needed": r["needed"]}
                for letter, r in scenarios.items()
            },
        }

    groups      = client.get_assignment_groups(course_id)
    submissions = client.get_submissions(course_id)
    weights     = _get_course_weights(inp, client)

    grade_result = _calc.current_grade(groups, submissions, weights)
    current_pct  = grade_result["weighted_grade"]

    # Identify the heaviest ungraded group as "the final"
    sub_by_id     = {s["assignment_id"]: s for s in submissions}
    weights_lower = {k.lower(): (k, v) for k, v in weights.items()}
    ungraded_groups = []
    for group in groups:
        scorable = [a for a in group.get("assignments", []) if a.get("points_possible", 0) > 0]
        # A group counts as ungraded if it has no assignments posted yet (final
        # exam not yet created) OR has at least one assignment without a score.
        no_assignments_posted = len(scorable) == 0
        has_unscored = any(
            sub_by_id.get(a["id"]) is None or sub_by_id[a["id"]].get("score") is None
            for a in scorable
        )
        if not (no_assignments_posted or has_unscored):
            continue
        name_lower = group["name"].lower()
        weight_key = None
        if name_lower in weights_lower:
            weight_key = weights_lower[name_lower][0]
        else:
            for k, (orig, _) in weights_lower.items():
                if k in name_lower:
                    weight_key = orig
                    break
        if weight_key is None:
            candidates = sorted(
                [(k, orig) for k, (orig, _) in weights_lower.items() if name_lower in k],
                key=lambda x: len(x[0]),
            )
            if candidates:
                weight_key = candidates[0][1]
        if weight_key:
            ungraded_groups.append((weights[weight_key], group["name"], weight_key))

    if not ungraded_groups:
        return {"error": "No ungraded assessments found"}

    ungraded_groups.sort(reverse=True)
    final_weight_pct, final_name, _ = ungraded_groups[0]
    final_weight = final_weight_pct / 100.0

    scenarios = _calc.grade_scenarios(current_pct, final_weight)

    return {
        "current_grade":    current_pct,
        "final_assessment": final_name,
        "final_weight_pct": final_weight_pct,
        "scenarios": {
            letter: {"status": r["status"], "needed": r["needed"]}
            for letter, r in scenarios.items()
        },
    }


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_HANDLERS = {
    "get_courses":              _get_courses,
    "get_academic_history":     _get_academic_history,
    "get_cached_grades":        _get_cached_grades,
    "get_all_grades":           _get_all_grades,
    "refresh_grades":           _refresh_grades,
    "get_all_announcements":     _get_all_announcements,
    "get_course_announcements": _get_course_announcements,
    "get_announcement_detail":  _get_announcement_detail,
    "get_course_weights":       _get_course_weights,
    "get_current_grade":        _get_current_grade,
    "get_grade_scenarios":      _get_grade_scenarios,
    "get_upcoming_deadlines":   _get_upcoming_deadlines_tool,
    "check_graduation_progress": _check_graduation_progress,
}

_USER_ID_TOOLS = {
    "get_courses", "get_cached_grades", "get_all_grades", "refresh_grades",
    "get_academic_history", "check_graduation_progress",
    "get_upcoming_deadlines", "get_all_announcements",
    "get_course_weights", "get_current_grade", "get_grade_scenarios",
}


def execute_tool(tool_name: str, tool_input: dict, client: QuercusClient, user_id: str | int | None = None):
    """Dispatch a tool call and return a JSON-serialisable result."""
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        if tool_name in _USER_ID_TOOLS:
            return handler(tool_input, client, user_id=user_id)
        return handler(tool_input, client)
    except Exception as exc:
        return {"error": str(exc)}
