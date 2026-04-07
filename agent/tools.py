"""
agent/tools.py — Claude tool definitions (JSON schemas) and dispatch.

TOOL_SCHEMAS  : list passed directly to the Anthropic messages API.
execute_tool  : called by the agent loop; accepts a QuercusClient so the
                token flows in from session state rather than from .env.
"""

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
            "graded submissions so far. Returns overall percentage, letter grade, "
            "and a per-group breakdown."
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


def _get_current_grade(inp: dict, client: QuercusClient) -> dict:
    course_id   = inp["course_id"]
    groups      = client.get_assignment_groups(course_id)
    submissions = client.get_submissions(course_id)
    weights     = _get_course_weights(inp, client)
    return _calc.current_grade(groups, submissions, weights)


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
    "get_course_weights":  _get_course_weights,
    "get_current_grade":   _get_current_grade,
    "get_grade_scenarios": _get_grade_scenarios,
}


def execute_tool(tool_name: str, tool_input: dict, client: QuercusClient):
    """Dispatch a tool call and return a JSON-serialisable result."""
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return handler(tool_input, client)
    except Exception as exc:
        return {"error": str(exc)}
