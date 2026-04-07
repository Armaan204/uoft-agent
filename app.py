"""
app.py — Streamlit chat interface for uoft-agent.
"""

import os
import secrets
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import streamlit as st
from dotenv import load_dotenv
from streamlit.errors import StreamlitSecretNotFoundError

from agent.agent import run
from calculator.grades import GradeCalculator
from integrations.acorn import AcornBackendError, get_import_status, get_latest_import
from integrations.quercus import QuercusClient, QuercusError
from integrations.syllabus import parse_syllabus_weights

load_dotenv()

try:
    ANTHROPIC_API_KEY = st.secrets.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
except StreamlitSecretNotFoundError:
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if ANTHROPIC_API_KEY:
    os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY

st.set_page_config(page_title="UofT Agent", page_icon="📚", layout="centered")


def _render_privacy_policy_page():
    """Render a standalone privacy policy page for the Chrome extension."""
    st.title("UofT Agent Connector Privacy Policy")
    st.caption("Last updated: 2026-04-07")

    st.markdown(
        """
        ## Summary

        UofT Agent Connector is a Chrome extension that helps a user import their
        own ACORN academic history into UofT Agent.

        The extension:

        - does not collect usernames or passwords
        - does not automate login
        - only runs on `https://acorn.utoronto.ca/*`
        - only imports data after the user has already logged in and manually clicks the import button
        - sends parsed academic-history data to the UofT Agent backend only after the user initiates the import

        ## What Data the Extension Processes

        When the user clicks **Import Academic History**, the extension may process:

        - course code
        - course title
        - credits / weight
        - mark
        - grade
        - raw course text needed for parsing
        - import code
        - timestamp
        - source page URL

        ## What Data the Extension Does Not Collect

        The extension does not collect:

        - ACORN usernames
        - ACORN passwords
        - browsing data from unrelated websites

        ## How Data Is Used

        Imported data is used only to let the user view their own ACORN academic
        history inside UofT Agent.

        ## Storage

        The extension may store:

        - the most recent import code in Chrome local storage
        - the most recent import payload for local extension flow support

        The backend may store imported academic-history data so the UofT Agent app
        can read it back using the same import code.

        ## User Control

        The extension only performs import when the user explicitly clicks the
        import button.
        """
    )


query_params = st.query_params
if query_params.get("page") == "privacy":
    _render_privacy_policy_page()
    st.stop()

# ---------------------------------------------------------------------------
# Onboarding — shown until a valid token is stored in session state
# ---------------------------------------------------------------------------

if "token" not in st.session_state:
    st.title("Welcome to UofT Agent")
    st.markdown(
        "Enter your Quercus personal access token to get started.  \n"
        "You can generate one at **q.utoronto.ca → Account → Settings → "
        "Under Approved Integrations → New Access Token**."
    )

    token_input = st.text_input("Quercus access token", type="password")

    if st.button("Connect"):
        if not token_input.strip():
            st.error("Please enter a token.")
        else:
            with st.spinner("Validating token..."):
                try:
                    QuercusClient(token=token_input.strip()).get_courses()
                    st.session_state.token = token_input.strip()
                    st.session_state.messages = []
                    st.rerun()
                except QuercusError:
                    st.error("Invalid token — please check and try again.")

    st.stop()

# ---------------------------------------------------------------------------
# Dashboard helpers
# ---------------------------------------------------------------------------

_calc = GradeCalculator()


def _risk_flag(pct: float, has_data: bool) -> tuple[str, str]:
    """Return (label, streamlit_color) based on current grade percentage."""
    if not has_data:
        return "Could not find syllabus", "gray"
    if pct < 70:
        return "At risk", "red"
    if pct < 85:
        return "On track", "orange"
    return "Safe", "green"


def _grade_from_points(groups: list, submissions: list) -> dict:
    """Total-points fallback: grade = sum(earned) / sum(possible) for graded work.

    Used when Canvas has no group weights and syllabus parsing is unavailable.
    Matches what Canvas shows in the grades tab for total-points courses.
    Returns a per-group breakdown so the UI can show the full calculation.

    Groups with the same name (Canvas allows duplicates) are merged so the
    breakdown stays consistent with the totals.
    """
    sub_by_id = {s["assignment_id"]: s for s in submissions}
    total_earned = total_possible = 0.0
    group_breakdown = {}

    for group in groups:
        g_earned = g_possible = 0.0
        for a in group.get("assignments", []):
            sub = sub_by_id.get(a["id"])
            if sub is None or sub.get("score") is None:
                continue
            g_earned   += sub["score"]
            g_possible += a.get("points_possible") or 0
        if g_possible == 0:
            continue
        gname = group["name"]
        if gname in group_breakdown:
            # Merge into existing entry — Canvas allows multiple groups with the same name
            group_breakdown[gname]["earned"]   += g_earned
            group_breakdown[gname]["possible"] += g_possible
            ep = group_breakdown[gname]["earned"] / group_breakdown[gname]["possible"]
            group_breakdown[gname]["pct"] = round(ep * 100, 2)
        else:
            group_breakdown[gname] = {
                "earned":   g_earned,
                "possible": g_possible,
                "pct":      round((g_earned / g_possible) * 100, 2),
            }
        total_earned   += g_earned
        total_possible += g_possible

    if total_possible == 0:
        return {"weighted_grade": 0.0, "letter": "N/A", "group_breakdown": {}, "graded_weight": 0.0}
    pct = (total_earned / total_possible) * 100
    return {
        "weighted_grade":  round(pct, 2),
        "letter":          GradeCalculator._to_letter(pct),
        "group_breakdown": group_breakdown,
        "graded_weight":   100.0,
        "_total_earned":   total_earned,
        "_total_possible": total_possible,
    }


def _resolve_course_weights(course_id: int, client: QuercusClient) -> tuple[dict | None, str | None]:
    """Resolve course weights from Canvas first, then from the syllabus."""
    weights = client.get_canvas_weights(course_id)
    if weights:
        return weights, "canvas"

    try:
        syllabus = client.get_syllabus(course_id)
        pdf_url = syllabus["pdf_urls"][0] if syllabus["pdf_urls"] else None
        _, weights = parse_syllabus_weights(course_id, client, pdf_url)
        if weights:
            return weights, "syllabus"
    except Exception:
        pass

    return None, None


def _display_grade_summary(grade: dict, grade_mode: str | None) -> tuple[bool, float, str, float]:
    """Return (has_data, displayed_pct, displayed_letter, graded_weight)."""
    has_data = grade is not None and grade["letter"] != "N/A"
    if not has_data:
        return False, 0.0, "N/A", 0.0

    graded_wt = grade.get("graded_weight", 0.0)
    if grade_mode == "weighted" and graded_wt > 0:
        earned_pts = grade["weighted_grade"] * graded_wt / 100
        pct = round(earned_pts + (100 - graded_wt), 2)
    else:
        pct = grade["weighted_grade"]
    return True, pct, GradeCalculator._to_letter(pct), graded_wt


def _load_single_course(course: dict, client: QuercusClient) -> dict:
    """Fetch grade data and upcoming deadlines for one course."""
    course_id = course["id"]
    result = {
        "id":          course_id,
        "name":        course["name"],
        "course_code": course.get("course_code", ""),
        "grade":       None,
        "grade_mode":  None,   # "weighted" or "total_points"
        "weights_source": None,
        "what_if_available": False,
        "what_if_reason": None,
        "error":       None,
        "deadlines":   [],
    }

    # --- Grade ---
    try:
        groups      = client.get_assignment_groups(course_id)
        submissions = client.get_submissions(course_id)

        weights, weights_source = _resolve_course_weights(course_id, client)
        result["weights_source"] = weights_source

        if weights:
            component_model = _calc.build_weighted_components(groups, submissions, weights)
            if component_model["reliable"]:
                result["what_if_available"] = True
            else:
                result["what_if_reason"] = "Weighted components could not be mapped reliably."

            grade = _calc.current_grade(groups, submissions, weights)
            # If all group names failed to match the weight keys the result is N/A;
            # fall back to raw points so the card never shows blank for a graded course.
            if grade["letter"] == "N/A":
                result["grade"]      = _grade_from_points(groups, submissions)
                result["grade_mode"] = "total_points"
            else:
                result["grade"]      = grade
                result["grade_mode"] = "weighted"
        else:
            # No Canvas weights and no accessible syllabus: omit overview grade.
            result["grade"]      = None
            result["grade_mode"] = None
            result["what_if_reason"] = "No Canvas weights or accessible syllabus weights found."
    except Exception as exc:
        result["error"] = str(exc)

    # --- Upcoming deadlines (non-fatal if it fails) ---
    try:
        now    = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=14)
        for a in client.get_assignments(course_id):
            due_raw = a.get("due_at")
            if not due_raw:
                continue
            due_dt = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
            if now <= due_dt <= cutoff:
                result["deadlines"].append({
                    "name":        a["name"],
                    "due_at":      due_dt,
                    "course_code": result["course_code"],
                })
    except Exception:
        pass

    return result


def _load_dashboard(token: str) -> tuple[list[dict], list[dict]]:
    """Fetch all course data in parallel. Returns (course_results, deadlines)."""
    client  = QuercusClient(token=token)
    courses = client.get_courses()
    n       = len(courses)

    course_results = [None] * n
    with ThreadPoolExecutor(max_workers=max(n, 1)) as pool:
        futures = {
            pool.submit(_load_single_course, c, client): i
            for i, c in enumerate(courses)
        }
        for future in as_completed(futures):
            course_results[futures[future]] = future.result()

    deadlines = sorted(
        [d for cr in course_results if cr for d in cr["deadlines"]],
        key=lambda d: d["due_at"],
    )
    return course_results, deadlines


def _load_course_detail(course_id: int, token: str) -> dict:
    """Load the data needed for a single course what-if page."""
    client = QuercusClient(token=token)
    courses = {c["id"]: c for c in client.get_courses()}
    course = courses.get(course_id)
    if course is None:
        raise QuercusError(f"Course {course_id} is not available in the current course list.")

    groups = client.get_assignment_groups(course_id)
    submissions = client.get_submissions(course_id)
    weights, weights_source = _resolve_course_weights(course_id, client)
    if not weights:
        return {
            "course": course,
            "weights_source": None,
            "available": False,
            "reason": "No Canvas weights or accessible syllabus weights found for this course.",
        }

    component_model = _calc.build_weighted_components(groups, submissions, weights)
    if not component_model["reliable"]:
        return {
            "course": course,
            "weights_source": weights_source,
            "available": False,
            "reason": "This course's weighted components could not be mapped reliably enough for sliders.",
            "component_model": component_model,
        }

    grade = _calc.current_grade(groups, submissions, weights)
    default_slider_values = {
        c["name"]: 100.0
        for c in component_model["components"]
        if c["status"] == "ungraded"
    }
    projected_default = _calc.projected_grade(
        component_model["components"],
        default_slider_values,
    )
    graded_weight = component_model["graded_weight"]

    return {
        "course": course,
        "weights_source": weights_source,
        "available": True,
        "grade": grade,
        "has_data": True,
        "current_standing": projected_default,
        "current_letter": GradeCalculator._to_letter(projected_default),
        "graded_weight": graded_weight,
        "component_model": component_model,
        "projected_default": projected_default,
    }


def _render_course_detail(course_id: int):
    """Render the dedicated what-if page for one course."""
    if st.button("Back to overview"):
        st.session_state.pop("selected_course_id", None)
        st.rerun()

    if "course_details" not in st.session_state:
        st.session_state.course_details = {}

    if course_id not in st.session_state.course_details:
        with st.spinner("Loading course details..."):
            st.session_state.course_details[course_id] = _load_course_detail(course_id, st.session_state.token)

    detail = st.session_state.course_details[course_id]
    course = detail["course"]
    code = course.get("course_code") or course.get("name")

    st.title(code)
    st.caption(course.get("name", ""))

    if not detail["available"]:
        st.warning(detail["reason"])
        component_model = detail.get("component_model")
        if component_model and component_model.get("unmatched_weights"):
            st.caption("Unmatched syllabus weights: " + ", ".join(component_model["unmatched_weights"]))
        return

    components = detail["component_model"]["components"]
    graded_components = [c for c in components if c["status"] == "graded"]
    ungraded_components = [c for c in components if c["status"] == "ungraded"]

    projected_inputs = {}
    for component in ungraded_components:
        key = f"what_if_{course_id}_{component['name']}"
        projected_inputs[component["name"]] = st.slider(
            f"{component['name']} ({component['weight']:.0f}%)",
            min_value=0,
            max_value=100,
            value=100,
            key=key,
        )

    projected_pct = _calc.projected_grade(components, projected_inputs)
    projected_letter = GradeCalculator._to_letter(projected_pct)

    metric_cols = st.columns(3)
    with metric_cols[0]:
        if detail["has_data"]:
            st.metric("Current standing", f"{detail['current_standing']:.1f}%", detail["current_letter"], delta_color="off")
        else:
            st.metric("Current standing", "—")
    with metric_cols[1]:
        st.metric("Projected final", f"{projected_pct:.1f}%", projected_letter, delta_color="off")
    with metric_cols[2]:
        delta = projected_pct - detail["current_standing"] if detail["has_data"] else None
        delta_text = f"{delta:+.1f} pts" if delta is not None else None
        st.metric("Weights source", detail["weights_source"].title(), delta_text, delta_color="off")

    st.subheader("Weighted Components")
    for component in graded_components:
        contrib = component["pct"] * component["weight"] / 100
        st.text(
            f"{component['name']} ({component['weight']:.0f}%): "
            f"{component['pct']:.1f}% completed -> {contrib:.1f} pts"
        )

    if ungraded_components:
        st.subheader("What-If Sliders")
        for component in ungraded_components:
            contrib = projected_inputs[component["name"]] * component["weight"] / 100
            st.text(
                f"{component['name']} ({component['weight']:.0f}%): "
                f"{projected_inputs[component['name']]:.0f}% -> {contrib:.1f} pts"
            )
    else:
        st.info("No ungraded weighted components remain for this course.")


def _get_acorn_import_code() -> str:
    """Return a stable per-session ACORN import code."""
    if "acorn_import_code" not in st.session_state:
        st.session_state.acorn_import_code = secrets.token_hex(4).upper()
    return st.session_state.acorn_import_code


def _load_acorn_data(import_code: str) -> dict:
    """Load the latest ACORN import for one import code."""
    try:
        return {
            "status": get_import_status(import_code),
            "latest": get_latest_import(import_code),
            "error": None,
        }
    except AcornBackendError as exc:
        return {
            "status": {"exists": False, "importedAt": None, "importCode": import_code},
            "latest": None,
            "error": str(exc),
        }


def _render_acorn_tab():
    """Render a minimal ACORN import/readback page."""
    import_code = _get_acorn_import_code()

    st.subheader("ACORN Import")
    st.info(
        "Use the UofT Agent Connector extension to import your ACORN academic history. "
        "The extension writes to the backend using your import code, and this page reads the latest imported data for that same code."
    )

    st.code(import_code, language=None)
    st.caption("Paste this import code into the extension popup before importing from ACORN.")

    st.markdown(
        "1. Install the Chrome extension from `uoft-acorn-extension/`  \n"
        "2. Open ACORN and log in normally  \n"
        "3. Paste the import code above into the extension popup  \n"
        "4. Click the extension's **Import Academic History** button  \n"
        "5. Return here and click **Refresh ACORN data**"
    )

    if "acorn_data" not in st.session_state:
        st.session_state.acorn_data = _load_acorn_data(import_code)

    if st.button("Refresh ACORN data", key="refresh_acorn_data"):
        st.session_state.acorn_data = _load_acorn_data(import_code)
        st.rerun()

    acorn_data = st.session_state.acorn_data
    status = acorn_data["status"]
    latest = acorn_data["latest"]

    if acorn_data.get("error"):
        st.error(
            "Could not load ACORN data from the backend. "
            f"{acorn_data['error']}"
        )
        return

    if not status.get("exists") or latest is None:
        st.warning(
            "No ACORN data has been imported for this code yet. If you have not installed the extension, "
            "install it first. Otherwise, paste this code into the extension, run the import from ACORN, "
            "then come back here and refresh."
        )
        return

    st.metric("Courses imported", len(latest.get("courses", [])))
    st.caption(f"Last import: {latest.get('importedAt') or 'Unknown'}")

    courses = latest.get("courses", [])
    if not courses:
        st.info("ACORN data exists, but no parsed courses were stored.")
        return

    rows = []
    for course in courses:
        rows.append({
            "Course": course.get("courseCode"),
            "Title": course.get("title"),
            "Credits": course.get("credits"),
            "Mark": course.get("mark"),
            "Grade": course.get("grade"),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Dashboard UI
# ---------------------------------------------------------------------------

if "selected_course_id" in st.session_state:
    _render_course_detail(int(st.session_state.selected_course_id))
    st.stop()

st.title("UofT Agent")

# Load (or retrieve cached) dashboard data
if "dashboard" not in st.session_state:
    with st.spinner("Loading your courses..."):
        st.session_state.dashboard = _load_dashboard(st.session_state.token)

course_results, deadlines = st.session_state.dashboard

main_tab, acorn_tab = st.tabs(["Dashboard", "ACORN"])

with main_tab:
    # Refresh button — top-right via columns
    hdr_col, btn_col = st.columns([5, 1])
    with hdr_col:
        st.subheader("Course Overview")
    with btn_col:
        if st.button("Refresh", use_container_width=True):
            del st.session_state["dashboard"]
            st.session_state.pop("course_details", None)
            st.rerun()

    # Course cards
    cols = st.columns(max(len(course_results), 1))
    for col, cr in zip(cols, course_results):
        with col:
            code  = cr["course_code"] or cr["name"]
            grade = cr.get("grade")
            has_data, pct, letter, graded_wt = _display_grade_summary(grade, cr.get("grade_mode"))

            risk_label, risk_color = _risk_flag(pct, has_data)

            st.markdown(f"**{code}**")
            if has_data:
                st.metric(label="Grade", value=f"{pct:.1f}%", delta=letter, delta_color="off", label_visibility="collapsed")
                st.progress(min(pct / 100.0, 1.0))
            else:
                st.markdown("**—**")
            st.markdown(f":{risk_color}[**{risk_label}**]")
            if cr.get("what_if_available"):
                if st.button("Grade breakdown", key=f"grade_breakdown_btn_{cr['id']}", use_container_width=True):
                    st.session_state.selected_course_id = cr["id"]
                    st.rerun()
            if cr.get("error"):
                st.caption(f"⚠ {cr['error'][:80]}")

    st.divider()

    # Upcoming deadlines
    st.subheader("Upcoming Deadlines — next 14 days")
    if deadlines:
        for d in deadlines:
            due_str = d["due_at"].strftime("%b %d, %Y %I:%M %p")
            st.markdown(f"**{d['course_code']}** &nbsp; {d['name']}  \n_{due_str} UTC_")
    else:
        st.info("No assignments due in the next 14 days.")

    st.divider()

    # ---------------------------------------------------------------------------
    # Chat UI
    # ---------------------------------------------------------------------------

    st.subheader("Ask the Agent")
    st.caption("Ask anything about your grades and courses")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Render conversation history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                for tc in msg.get("tool_calls", []):
                    label = "🔧 {}({})".format(
                        tc["name"],
                        ", ".join(f"{k}={v}" for k, v in tc["input"].items()),
                    )
                    with st.expander(label, expanded=False):
                        st.json(tc["result"])
            st.markdown(msg["content"])

    # New message
    if prompt := st.chat_input("Ask about your grades..."):
        st.session_state.messages.append({"role": "user", "content": prompt, "tool_calls": []})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer, tool_calls = run(
                    prompt,
                    token=st.session_state.token,
                    verbose=False,
                    return_tool_calls=True,
                )

            for tc in tool_calls:
                label = "🔧 {}({})".format(
                    tc["name"],
                    ", ".join(f"{k}={v}" for k, v in tc["input"].items()),
                )
                with st.expander(label, expanded=False):
                    st.json(tc["result"])

            st.markdown(answer)

        st.session_state.messages.append({
            "role":       "assistant",
            "content":    answer,
            "tool_calls": tool_calls,
        })

with acorn_tab:
    _render_acorn_tab()
