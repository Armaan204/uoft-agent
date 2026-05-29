"""
agent/tools.py — Claude tool definitions (JSON schemas) and dispatch.

TOOL_SCHEMAS  : list passed directly to the Anthropic messages API.
execute_tool  : called by the agent loop; accepts a QuercusClient so the
                token flows in from session state rather than from .env.
"""

import re
from datetime import datetime, timedelta, timezone
from html import unescape

from api.services.acorn_service import get_academic_history as load_academic_history
from api.services.grade_snapshot_cache import get_grade_snapshot, invalidate_grade_snapshot
from api.services.grades_snapshot_service import get_snapshot as load_grades_snapshot, save_snapshot
from api.integrations.graduation_service import check_graduation_progress as _check_grad_progress
from api.integrations.graduation_service import get_program_requirements as _get_prog_reqs
from api.integrations.quercus import QuercusClient
from api.integrations.syllabus import parse_syllabus_weights
from api.calculator.grades import GradeCalculator

_calc = GradeCalculator()

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

def _get_courses(inp: dict, client: QuercusClient) -> list:
    courses = client.get_courses()
    return [
        {"id": c["id"], "name": c["name"], "course_code": c["course_code"]}
        for c in courses
    ]


def _get_course_weights(inp: dict, client: QuercusClient) -> dict:
    course_id = inp["course_id"]

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


def _get_current_grade(inp: dict, client: QuercusClient) -> dict:
    course_id   = inp["course_id"]
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
    if not snapshot_rows:
        return {"courses": [], "errors": [], "fetched_at": None}

    fetched_values = [row.get("fetched_at") for row in snapshot_rows if row.get("fetched_at")]
    fetched_at = max(fetched_values) if fetched_values else None

    return {
        "courses": [
            {
                "course_id": row["course_id"],
                "course_name": row.get("course_name"),
                "course_code": row.get("course_code"),
                "current_grade": row.get("current_grade"),
                "letter": row.get("letter_grade"),
                "graded_weight": None,
            }
            for row in snapshot_rows
        ],
        "errors": [],
        "fetched_at": fetched_at,
    }


def _get_all_grades(inp: dict, client: QuercusClient, user_id: str | int | None = None) -> dict:
    if user_id is not None:
        return get_grade_snapshot(user_id, client._token)

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
        "courses": grades,
        "errors": errors,
    }


def _refresh_grades(inp: dict, client: QuercusClient, user_id: str | int | None = None) -> dict:
    if user_id is None:
        return _get_all_grades(inp, client, user_id=None)

    invalidate_grade_snapshot(user_id)
    fresh = get_grade_snapshot(user_id, client._token, force_refresh=True)
    save_snapshot(user_id, fresh.get("courses", []))
    return fresh


def _get_all_announcements(inp: dict, client: QuercusClient, user_id: str | int | None = None) -> dict:
    # Fast path: read from dashboard snapshot (already aggregated, zero API calls)
    if user_id is not None:
        snapshot_rows = load_grades_snapshot(user_id)
        for row in snapshot_rows:
            if row.get("announcements") is not None:
                return {"announcements": row["announcements"], "source": "snapshot"}

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


def _get_grade_scenarios(inp: dict, client: QuercusClient) -> dict:
    course_id   = inp["course_id"]
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
    "get_cached_grades", "get_all_grades", "refresh_grades",
    "get_academic_history", "check_graduation_progress",
    "get_upcoming_deadlines", "get_all_announcements",
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
