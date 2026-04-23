"""
agent/tools.py — Claude tool definitions (JSON schemas) and dispatch.

TOOL_SCHEMAS  : list passed directly to the Anthropic messages API.
execute_tool  : called by the agent loop; accepts a QuercusClient so the
                token flows in from session state rather than from .env.
"""

import re
from html import unescape

from api.services.acorn_service import get_academic_history as load_academic_history
from api.services.grade_snapshot_cache import get_grade_snapshot, invalidate_grade_snapshot
from api.services.grades_snapshot_service import get_snapshot as load_grades_snapshot, save_snapshot
from integrations.quercus import QuercusClient
from integrations.syllabus import parse_syllabus_weights
from calculator.grades import GradeCalculator

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
            "credits earned, and GPA by term. Prefer this for past performance and GPA history questions."
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
        "name": "get_course_announcements",
        "description": (
            "Return up to 10 recent announcements for one course as lightweight previews. "
            "Prefer this when the user asks about course news or instructor updates."
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
    "get_courses":         _get_courses,
    "get_academic_history": _get_academic_history,
    "get_cached_grades":   _get_cached_grades,
    "get_all_grades":      _get_all_grades,
    "refresh_grades":      _refresh_grades,
    "get_course_announcements": _get_course_announcements,
    "get_announcement_detail": _get_announcement_detail,
    "get_course_weights":  _get_course_weights,
    "get_current_grade":   _get_current_grade,
    "get_grade_scenarios": _get_grade_scenarios,
}


def execute_tool(tool_name: str, tool_input: dict, client: QuercusClient, user_id: str | int | None = None):
    """Dispatch a tool call and return a JSON-serialisable result."""
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        if tool_name in {"get_cached_grades", "get_all_grades", "refresh_grades", "get_academic_history"}:
            return handler(tool_input, client, user_id=user_id)
        return handler(tool_input, client)
    except Exception as exc:
        return {"error": str(exc)}
