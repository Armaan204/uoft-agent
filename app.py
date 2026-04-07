"""
app.py — Streamlit chat interface for uoft-agent.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import streamlit as st
from dotenv import load_dotenv

from agent.agent import run
from calculator.grades import GradeCalculator
from integrations.quercus import QuercusClient, QuercusError
from integrations.syllabus import parse_syllabus_weights

load_dotenv()

st.set_page_config(page_title="UofT Agent", page_icon="📚", layout="centered")

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
        return "No data", "gray"
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


def _load_single_course(course: dict, client: QuercusClient) -> dict:
    """Fetch grade data and upcoming deadlines for one course."""
    course_id = course["id"]
    result = {
        "id":          course_id,
        "name":        course["name"],
        "course_code": course.get("course_code", ""),
        "grade":       None,
        "grade_mode":  None,   # "weighted" or "total_points"
        "error":       None,
        "deadlines":   [],
    }

    # --- Grade ---
    try:
        groups      = client.get_assignment_groups(course_id)
        submissions = client.get_submissions(course_id)

        weights = client.get_canvas_weights(course_id)
        if not weights:
            # Try syllabus parsing — non-fatal if it fails
            try:
                syllabus = client.get_syllabus(course_id)
                pdf_url  = syllabus["pdf_urls"][0] if syllabus["pdf_urls"] else None
                _, weights = parse_syllabus_weights(course_id, client, pdf_url)
            except Exception:
                weights = None  # will use total-points fallback below

        if weights:
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
            # Canvas total-points course with no accessible syllabus
            result["grade"]      = _grade_from_points(groups, submissions)
            result["grade_mode"] = "total_points"
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


# ---------------------------------------------------------------------------
# Dashboard UI
# ---------------------------------------------------------------------------

st.title("UofT Agent")

# Load (or retrieve cached) dashboard data
if "dashboard" not in st.session_state:
    with st.spinner("Loading your courses..."):
        st.session_state.dashboard = _load_dashboard(st.session_state.token)

course_results, deadlines = st.session_state.dashboard

# Refresh button — top-right via columns
hdr_col, btn_col = st.columns([5, 1])
with hdr_col:
    st.subheader("Course Overview")
with btn_col:
    if st.button("Refresh", use_container_width=True):
        del st.session_state["dashboard"]
        st.rerun()

# Course cards
cols = st.columns(max(len(course_results), 1))
for col, cr in zip(cols, course_results):
    with col:
        code  = cr["course_code"] or cr["name"]
        grade = cr.get("grade")
        has_data = grade is not None and grade["letter"] != "N/A"

        if has_data:
            graded_wt = grade.get("graded_weight", 0)
            if cr.get("grade_mode") == "weighted" and graded_wt > 0:
                # Accumulated grade: points earned so far + full credit on ungraded work.
                # Equivalent to "start at 100%, subtract marks lost on assessed items."
                earned_pts = grade["weighted_grade"] * graded_wt / 100
                pct = round(earned_pts + (100 - graded_wt), 2)
            else:
                pct = grade["weighted_grade"]
            letter = GradeCalculator._to_letter(pct)
        else:
            pct, letter, graded_wt = 0.0, "N/A", 0

        risk_label, risk_color = _risk_flag(pct, has_data)

        st.markdown(f"**{code}**")
        if has_data:
            st.metric(label="Grade", value=f"{pct:.1f}%", delta=letter, delta_color="off", label_visibility="collapsed")
            st.progress(min(pct / 100.0, 1.0))
        else:
            st.markdown("**—**")
        st.markdown(f":{risk_color}[**{risk_label}**]")
        if has_data:
            breakdown = grade.get("group_breakdown", {})
            with st.expander("Grade breakdown"):
                if cr.get("grade_mode") == "total_points":
                    st.caption("No syllabus weights — grade = total earned ÷ total possible")
                    for gname, g in breakdown.items():
                        st.text(f"{gname}: {g['earned']:.1f} / {g['possible']:.1f} pts  ({g['pct']:.1f}%)")
                    total_e = grade.get("_total_earned", 0)
                    total_p = grade.get("_total_possible", 0)
                    st.markdown(f"**Total: {total_e:.1f} / {total_p:.1f} = {pct:.1f}%**")
                else:
                    earned_pts = 0.0
                    for gname, g in breakdown.items():
                        if g["weight"] == 0:
                            continue
                        contrib = g["pct"] * g["weight"] / 100
                        earned_pts += contrib
                        st.text(
                            f"{gname} ({g['weight']:.0f}%):  "
                            f"{g['earned']:.1f}/{g['possible']:.1f}  "
                            f"= {g['pct']:.1f}%  →  {contrib:.1f} pts"
                        )
                    ungraded_wt = 100 - graded_wt
                    if ungraded_wt > 0:
                        st.text(f"Remaining ({ungraded_wt:.0f}%):  not yet assessed  →  {ungraded_wt:.1f} pts assumed")
                    st.markdown(f"**Current standing: {pct:.1f}%**")
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
