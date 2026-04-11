"""
app.py — Streamlit chat interface for uoft-agent.
"""

import traceback
import os
import secrets
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from time import perf_counter

try:
    import streamlit as st
except Exception:
    print("Failed to import streamlit in app.py", flush=True)
    traceback.print_exc()
    raise

try:
    from bs4 import BeautifulSoup
except Exception:
    print("Failed to import BeautifulSoup in app.py", flush=True)
    traceback.print_exc()
    raise

try:
    from dotenv import load_dotenv
except Exception:
    print("Failed to import load_dotenv in app.py", flush=True)
    traceback.print_exc()
    raise

try:
    from streamlit.errors import StreamlitSecretNotFoundError
except Exception:
    print("Failed to import StreamlitSecretNotFoundError in app.py", flush=True)
    traceback.print_exc()
    raise

try:
    load_dotenv()
except Exception:
    print("Failed during load_dotenv() in app.py", flush=True)
    traceback.print_exc()
    raise


def _env_present(name: str) -> bool:
    try:
        secret_value = st.secrets.get(name)
    except StreamlitSecretNotFoundError:
        secret_value = None
    return bool(secret_value or os.getenv(name))


def _print_startup_env_debug() -> dict[str, bool]:
    status = {
        "ANTHROPIC_API_KEY": _env_present("ANTHROPIC_API_KEY"),
        "SUPABASE_URL": _env_present("SUPABASE_URL"),
        "SUPABASE_KEY": _env_present("SUPABASE_KEY"),
        "ENCRYPTION_KEY": _env_present("ENCRYPTION_KEY"),
    }
    print(f"Startup env presence: {status}", flush=True)
    return status


try:
    STARTUP_ENV_STATUS = _print_startup_env_debug()
except Exception:
    print("Failed during startup env debug in app.py", flush=True)
    traceback.print_exc()
    raise

try:
    ANTHROPIC_API_KEY = st.secrets.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
except StreamlitSecretNotFoundError:
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
except Exception:
    print("Failed while resolving ANTHROPIC_API_KEY in app.py", flush=True)
    traceback.print_exc()
    raise
if ANTHROPIC_API_KEY:
    os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY

for env_name in ("SUPABASE_URL", "SUPABASE_KEY", "ENCRYPTION_KEY", "ACORN_BACKEND_URL"):
    try:
        env_value = st.secrets.get(env_name) or os.getenv(env_name)
    except StreamlitSecretNotFoundError:
        env_value = os.getenv(env_name)
    except Exception:
        print(f"Failed while resolving {env_name} in app.py", flush=True)
        traceback.print_exc()
        raise
    if env_value:
        os.environ[env_name] = str(env_value)

try:
    st.set_page_config(page_title="UofT Agent", page_icon="📚", layout="centered")
except Exception:
    print("Failed during st.set_page_config() in app.py", flush=True)
    traceback.print_exc()
    raise

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


# ---------------------------------------------------------------------------
# Deferred imports
# ---------------------------------------------------------------------------

_calc = None


def _get_grade_calculator():
    global _calc
    if _calc is None:
        from calculator.grades import GradeCalculator
        _calc = GradeCalculator()
    return _calc


def _to_letter(pct: float) -> str:
    from calculator.grades import GradeCalculator
    return GradeCalculator._to_letter(pct)


def _get_quercus_types():
    from integrations.quercus import QuercusClient, QuercusError
    return QuercusClient, QuercusError


def _parse_syllabus_weights_lazy(course_id, client, pdf_url=None):
    from integrations.syllabus import parse_syllabus_weights
    return parse_syllabus_weights(course_id, client, pdf_url)


def _get_acorn_helpers():
    from integrations.acorn import AcornBackendError, get_import_status, get_latest_import
    return AcornBackendError, get_import_status, get_latest_import


def _run_agent(*args, **kwargs):
    from agent.agent import run
    return run(*args, **kwargs)


def _get_user_store():
    from auth.user_store import (
        UserStoreError,
        delete_quercus_token,
        get_or_create_user,
        get_quercus_token,
        save_quercus_token,
    )
    return UserStoreError, get_or_create_user, get_quercus_token, save_quercus_token, delete_quercus_token


def _get_grades_cache_helpers():
    from integrations.grades_cache import (
        GradesCacheError,
        detect_new_grades,
        get_grade_overrides,
        get_saved_grades,
        save_grade_override,
        save_grades,
    )
    return (
        GradesCacheError,
        detect_new_grades,
        get_grade_overrides,
        get_saved_grades,
        save_grade_override,
        save_grades,
    )


def _clear_quercus_session_state():
    """Clear cached state derived from the current Quercus token."""
    for key in [
        "token",
        "dashboard",
        "course_details",
        "selected_course_id",
        "messages",
    ]:
        st.session_state.pop(key, None)


def _ensure_app_user() -> dict:
    """Ensure the Streamlit-authenticated user exists in Supabase."""
    if "app_user" in st.session_state:
        return st.session_state.app_user

    UserStoreError, get_or_create_user, _, _, _ = _get_user_store()
    google_id = getattr(st.user, "sub", None)
    email = getattr(st.user, "email", None)
    if not google_id:
        raise UserStoreError("Logged-in user is missing st.user.sub")

    user = get_or_create_user(google_id, email)
    st.session_state.app_user = user
    st.session_state.user_id = user["id"]
    return user


def _restore_persisted_quercus_token() -> None:
    """Load a persisted token from Supabase into session state if present."""
    if "token" in st.session_state:
        return

    user = _ensure_app_user()
    _, _, get_quercus_token, _, _ = _get_user_store()
    token = get_quercus_token(user["id"])
    if token:
        st.session_state.token = token


def _disconnect_quercus() -> None:
    """Delete the persisted token and clear all local Quercus-derived state."""
    _, _, _, _, delete_quercus_token = _get_user_store()
    user_id = st.session_state.get("user_id")
    if user_id is not None:
        delete_quercus_token(user_id)
    _clear_quercus_session_state()


def _is_invalid_quercus_token_error(exc: Exception) -> bool:
    """Return True when a Quercus error indicates an expired/revoked token."""
    message = str(exc).lower()
    return "401" in message or "revoked access token" in message or "unauthorized" in message


def _expire_quercus_token(message: str) -> None:
    """Clear the persisted/session token and return the user to onboarding."""
    user_id = st.session_state.get("user_id")
    if user_id is not None:
        try:
            _, _, _, _, delete_quercus_token = _get_user_store()
            delete_quercus_token(user_id)
        except Exception:
            pass
    _clear_quercus_session_state()
    if "app_user" in st.session_state:
        st.session_state.user_id = st.session_state.app_user["id"]
    st.session_state.token_error = message


def _risk_flag(pct: float, has_data: bool) -> tuple[str, str]:
    """Return (label, streamlit_color) based on current grade percentage."""
    if not has_data:
        return "No breakdown", "gray"
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
        "letter":          _to_letter(pct),
        "group_breakdown": group_breakdown,
        "graded_weight":   100.0,
        "_total_earned":   total_earned,
        "_total_possible": total_possible,
    }


def _grade_from_components(components: list[dict]) -> dict:
    """Build a grade summary from a reliable weighted component model."""
    graded_components = [c for c in components if c["status"] == "graded"]
    graded_weight = sum(c["weight"] for c in graded_components)
    if graded_weight <= 0:
        return {
            "weighted_grade": 0.0,
            "letter": "N/A",
            "group_breakdown": {},
            "graded_weight": 0.0,
        }

    weighted_sum = sum(c["pct"] * c["weight"] for c in graded_components)
    weighted_grade = weighted_sum / graded_weight
    return {
        "weighted_grade": round(weighted_grade, 2),
        "letter": _to_letter(weighted_grade),
        "group_breakdown": {
            c["name"]: {
                "earned": c["earned"],
                "possible": c["possible"],
                "pct": c["pct"],
                "weight": c["weight"],
            }
            for c in graded_components
        },
        "graded_weight": round(graded_weight, 2),
    }


def _apply_grade_overrides(components: list[dict], overrides: dict[str, dict]) -> list[dict]:
    """Return component copies with manual overrides applied for calculations."""
    applied = []
    for component in components:
        clone = dict(component)
        clone["is_manual"] = False
        clone["manual_score"] = None
        clone["manual_possible"] = None
        override = overrides.get(clone.get("component_key"))
        if override:
            manual_score = override.get("manual_score")
            manual_possible = override.get("manual_possible")
            if manual_score is not None and manual_possible not in (None, 0):
                clone["earned"] = manual_score
                clone["possible"] = manual_possible
                clone["pct"] = round((manual_score / manual_possible) * 100, 2)
                clone["status"] = "graded"
                clone["is_manual"] = True
                clone["manual_score"] = manual_score
                clone["manual_possible"] = manual_possible
        applied.append(clone)
    return applied


def _resolve_course_weights(course_id: int, client) -> tuple[dict | None, str | None]:
    """Resolve course weights from Canvas first, then from the syllabus."""
    from integrations.syllabus import SyllabusError
    weights = client.get_canvas_weights(course_id)
    if weights:
        return weights, "canvas"

    try:
        syllabus = client.get_syllabus(course_id)
        pdf_url = syllabus["pdf_urls"][0] if syllabus["pdf_urls"] else None
        _, weights = _parse_syllabus_weights_lazy(course_id, client, pdf_url)
        if weights:
            return weights, "syllabus"
    except SyllabusError:
        # No syllabus found — not an error, just no weights available.
        pass
    # All other exceptions (API errors, rate limits, etc.) propagate so they
    # surface as a visible error on the dashboard card instead of silent failure.

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
    return True, pct, _to_letter(pct), graded_wt


def _load_single_course(course: dict, client) -> dict:
    """Fetch grade data and upcoming deadlines for one course."""
    started_at = perf_counter()
    calc = _get_grade_calculator()
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
            component_model = calc.build_weighted_components(groups, submissions, weights)
            if component_model["reliable"]:
                result["what_if_available"] = True
                result["grade"]      = _grade_from_components(component_model["components"])
                result["grade_mode"] = "weighted"
            else:
                result["what_if_reason"] = "Weighted components could not be mapped reliably."
        else:
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
                    "url":         a.get("html_url"),
                })
    except Exception:
        pass

    elapsed = perf_counter() - started_at
    code = result["course_code"] or result["name"] or str(course_id)
    print(f"Course load timing: {code} ({course_id}) in {elapsed:.2f}s", flush=True)
    return result


def _announcement_preview(html: str | None, limit: int = 180) -> str:
    """Convert announcement HTML into a compact plain-text preview."""
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _load_dashboard(token: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Fetch all course data in parallel. Returns (course_results, deadlines, announcements)."""
    started_at = perf_counter()
    QuercusClient, _ = _get_quercus_types()
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

    announcements = []
    course_lookup = {c["id"]: c for c in courses}
    try:
        raw_announcements = client.get_latest_announcements(list(course_lookup.keys()))
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
                "posted_at": posted_dt,
            })
    except Exception:
        announcements = []

    announcements.sort(
        key=lambda a: a["posted_at"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    total_elapsed = perf_counter() - started_at
    print(
        f"Dashboard load timing: {len(course_results)} courses in {total_elapsed:.2f}s",
        flush=True,
    )
    return course_results, deadlines, announcements


def _load_course_detail(course_id: int, token: str, user_id: str | int) -> dict:
    """Load the data needed for a single course what-if page."""
    calc = _get_grade_calculator()
    QuercusClient, QuercusError = _get_quercus_types()
    (
        _GradesCacheError,
        detect_new_grades,
        get_grade_overrides,
        get_saved_grades,
        _save_grade_override,
        _save_grades,
    ) = _get_grades_cache_helpers()
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

    component_model = calc.build_weighted_components(groups, submissions, weights)
    if not component_model["reliable"]:
        return {
            "course": course,
            "weights_source": weights_source,
            "available": False,
            "reason": "This course's weighted components could not be mapped reliably enough for sliders.",
            "component_model": component_model,
        }

    saved_grades = get_saved_grades(user_id, course_id)
    overrides = get_grade_overrides(user_id, course_id)
    live_components = component_model["components"]
    components = _apply_grade_overrides(live_components, overrides)
    live_new_grade_keys = set(detect_new_grades(user_id, course_id, live_components))
    grade = _grade_from_components(components)
    default_slider_values = {
        c["component_key"]: 100.0
        for c in components
        if c["status"] == "ungraded"
    }
    projected_default = calc.projected_grade(
        components,
        default_slider_values,
    )
    graded_weight = round(sum(c["weight"] for c in components if c["status"] == "graded"), 2)

    return {
        "course": course,
        "weights_source": weights_source,
        "available": True,
        "grade": grade,
        "has_data": True,
        "current_standing": projected_default,
        "current_letter": _to_letter(projected_default),
        "graded_weight": graded_weight,
        "component_model": {**component_model, "components": components},
        "live_components": live_components,
        "projected_default": projected_default,
        "saved_grades": saved_grades,
        "overrides": overrides,
        "new_grade_keys": live_new_grade_keys,
    }


def _render_course_detail(course_id: int):
    """Render the dedicated what-if page for one course."""
    calc = _get_grade_calculator()
    st.markdown(
        """
        <style>
        .component-meta {
            margin: -0.35rem 0 0.15rem 0;
            color: rgb(107, 114, 128);
            font-size: 0.875rem;
        }
        div[data-testid="stElementContainer"]:has(.moved-slider-marker)
          + div[data-testid="stElementContainer"] [data-baseweb="slider"] {
            filter: grayscale(1) saturate(0.1);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Back to overview"):
        st.session_state.pop("selected_course_id", None)
        st.rerun()

    if "course_details" not in st.session_state:
        st.session_state.course_details = {}

    if course_id not in st.session_state.course_details:
        with st.spinner("Loading course details..."):
            st.session_state.course_details[course_id] = _load_course_detail(
                course_id,
                st.session_state.token,
                st.session_state.user_id,
            )

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
    (
        GradesCacheError,
        _detect_new_grades,
        _get_grade_overrides,
        _get_saved_grades,
        save_grade_override,
        save_grades,
    ) = _get_grades_cache_helpers()

    projected_inputs = {}
    for component in graded_components:
        component_key = component["component_key"]
        projected_inputs[component_key] = st.session_state.get(
            f"what_if_{course_id}_{component_key}",
            int(round(component["pct"])),
        )
    for component in ungraded_components:
        component_key = component["component_key"]
        projected_inputs[component_key] = st.session_state.get(
            f"what_if_{course_id}_{component_key}",
            100,
        )

    projected_pct = calc.projected_grade(components, projected_inputs)
    projected_letter = _to_letter(projected_pct)

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

    if graded_components:
        st.subheader("Marked Components")
        for component in graded_components:
            component_key = component["component_key"]
            label = component["name"]
            if component_key in detail.get("new_grade_keys", set()):
                label += " 🆕"

            st.markdown(f"**{label}**")
            baseline_value = int(round(component["pct"]))
            current_value = st.session_state.get(
                f"what_if_{course_id}_{component_key}",
                baseline_value,
            )
            meta_class = "component-meta moved-slider-marker" if current_value != baseline_value else "component-meta"
            st.markdown(
                (
                    f'<p class="{meta_class}">'
                    f"Weight: {component['weight']:.2f}%, "
                    f"Score: {component['earned']:.1f}/{component['possible']:.1f} pts"
                    f"</p>"
                ),
                unsafe_allow_html=True,
            )

            key = f"what_if_{course_id}_{component_key}"
            projected_inputs[component_key] = st.slider(
                "Slider",
                min_value=0,
                max_value=100,
                value=baseline_value,
                key=key,
                label_visibility="collapsed",
            )

        if st.button("Save grades", use_container_width=True):
            try:
                for component in graded_components:
                    slider_pct = float(projected_inputs[component["component_key"]])
                    possible = float(component.get("possible") or 0.0)
                    if possible <= 0:
                        continue
                    save_grade_override(
                        st.session_state.user_id,
                        course_id,
                        component["component_key"],
                        round(possible * slider_pct / 100.0, 2),
                        possible,
                    )
                live_graded_components = [
                    component
                    for component in detail.get("live_components", [])
                    if component.get("status") == "graded"
                ]
                save_grades(st.session_state.user_id, course_id, live_graded_components)
            except GradesCacheError as exc:
                st.error(f"Could not save grades. {exc}")
            else:
                st.session_state.pop("dashboard", None)
                st.session_state.course_details.pop(course_id, None)
                st.rerun()

        st.warning("Grades are estimated from Quercus data and may not reflect your official grade.")

    if ungraded_components:
        st.subheader("Remaining Components")
    for component in ungraded_components:
        component_key = component["component_key"]
        current_value = st.session_state.get(f"what_if_{course_id}_{component_key}", 100)
        if current_value != 100:
            st.markdown('<p class="component-meta moved-slider-marker"></p>', unsafe_allow_html=True)
        key = f"what_if_{course_id}_{component_key}"
        projected_inputs[component_key] = st.slider(
            f"{component['name']} ({component['weight']:.2f}%)",
            min_value=0,
            max_value=100,
            value=100,
            key=key,
        )
        contrib = projected_inputs[component_key] * component["weight"] / 100
        st.caption(
            f"Using {projected_inputs[component_key]:.0f}% "
            f"({contrib:.1f} pts)"
        )
    if not ungraded_components:
        st.info("No remaining weighted components for this course.")


def _get_acorn_import_code() -> str:
    """Return a stable per-session ACORN import code."""
    if "acorn_import_code" not in st.session_state:
        st.session_state.acorn_import_code = secrets.token_hex(4).upper()
    return st.session_state.acorn_import_code


def _load_acorn_data(import_code: str) -> dict:
    """Load the latest ACORN import for one import code."""
    AcornBackendError, get_import_status, get_latest_import = _get_acorn_helpers()
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


def main():
    query_params = st.query_params
    if query_params.get("page") == "privacy":
        _render_privacy_policy_page()
        st.stop()

    if not st.user.is_logged_in:
        st.title("UofT Agent")
        st.subheader("Demo:")
        st.markdown(
            """
            <style>
            img {
                border: 4px solid #2b2a29;
                border-radius: 10px;
                padding: 4px;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.image("assets/demo.gif")
        st.markdown(
            """
            <style>
            div[data-testid="stButton"] > button[kind="secondary"] {
                background-color: #c0392b;
                color: white;
                font-size: 1.1rem;
                font-weight: 600;
                padding: 0.65rem 2.5rem;
                border: none;
                border-radius: 6px;
                display: block;
                margin: 1rem auto;
                cursor: pointer;
            }
            div[data-testid="stButton"] > button[kind="secondary"]:hover {
                background-color: #a93226;
                color: white;
            }
            div[data-testid="stButton"] {
                text-align: center;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        # Centering
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.button("Sign in with Google", on_click=st.login, args=("google",))
        st.stop()

    try:
        _ensure_app_user()
        _restore_persisted_quercus_token()
    except Exception as exc:
        st.error(f"Could not load your account data. {exc}")
        st.stop()

    with st.sidebar:
        st.markdown(f"**{st.user.name}**")
        st.caption(st.user.email)
        if "token" in st.session_state:
            if st.button("Disconnect Quercus", use_container_width=True):
                try:
                    _disconnect_quercus()
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not disconnect Quercus. {exc}")
        if st.button("Log out", use_container_width=True):
            _clear_quercus_session_state()
            st.session_state.pop("app_user", None)
            st.session_state.pop("user_id", None)
            st.logout()

    # -----------------------------------------------------------------------
    # Onboarding — shown until a valid token is stored in session state
    # -----------------------------------------------------------------------
    if "token" not in st.session_state:
        QuercusClient, QuercusError = _get_quercus_types()
        st.title("Welcome to UofT Agent")
        if st.session_state.get("token_error"):
            st.error(st.session_state.pop("token_error"))
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
                        _, _, _, save_quercus_token, _ = _get_user_store()
                        save_quercus_token(st.session_state.user_id, token_input.strip())
                        _clear_quercus_session_state()
                        st.session_state.app_user = _ensure_app_user()
                        st.session_state.user_id = st.session_state.app_user["id"]
                        st.session_state.token = token_input.strip()
                        st.session_state.messages = []
                        st.rerun()
                    except QuercusError:
                        st.error("Invalid token — please check and try again.")
                    except Exception as exc:
                        st.error(f"Could not save token. {exc}")

        st.stop()

    # -----------------------------------------------------------------------
    # Dashboard UI
    # -----------------------------------------------------------------------
    if "selected_course_id" in st.session_state:
        try:
            _render_course_detail(int(st.session_state.selected_course_id))
        except Exception as exc:
            if _is_invalid_quercus_token_error(exc):
                _expire_quercus_token(
                    "Your Quercus token expired or was revoked. Please enter a new token."
                )
                st.rerun()
            raise
        st.stop()

    st.markdown(
        """
        <div style="display:flex; justify-content:space-between; align-items:center; gap:1rem; margin-bottom:1rem;">
          <h1 style="margin:0;">UofT Agent</h1>
          <a
            href="https://forms.gle/TuLNGSS7nGD3ik237"
            target="_blank"
            style="
              display:inline-flex;
              align-items:center;
              justify-content:center;
              padding:0.65rem 1rem;
              border:1px solid #d97706;
              border-radius:999px;
              text-decoration:none;
              color:#7c2d12;
              background:linear-gradient(135deg, #fef3c7 0%, #fdba74 100%);
              box-shadow:0 8px 20px rgba(217, 119, 6, 0.18);
              font-weight:700;
              white-space:nowrap;
              transition:transform 0.15s ease, box-shadow 0.15s ease;
            "
            title="Takes 1 minute. Helps improve the app."
          >
            📝 Give Feedback
          </a>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "dashboard" not in st.session_state:
        try:
            with st.spinner("Loading your courses..."):
                st.session_state.dashboard = _load_dashboard(st.session_state.token)
        except Exception as exc:
            if _is_invalid_quercus_token_error(exc):
                _expire_quercus_token(
                    "Your Quercus token expired or was revoked. Please enter a new token."
                )
                st.rerun()
            raise

    course_results, deadlines, announcements = st.session_state.dashboard

    main_tab, acorn_tab = st.tabs(["Dashboard", "ACORN"])

    with main_tab:
        hdr_col, btn_col = st.columns([5, 1])
        with hdr_col:
            st.subheader("Course Overview")
        with btn_col:
            if st.button("Refresh", use_container_width=True):
                del st.session_state["dashboard"]
                st.session_state.pop("course_details", None)
                st.rerun()

        cols = st.columns(max(len(course_results), 1))
        for col, cr in zip(cols, course_results):
            with col:
                code = cr["course_code"] or cr["name"]
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

        st.subheader("Upcoming Deadlines — next 14 days")
        if deadlines:
            for d in deadlines:
                due_str = d["due_at"].strftime("%b %d, %Y %I:%M %p")
                title = d["name"]
                if d.get("url"):
                    title = f"[{title}]({d['url']})"
                st.markdown(f"- **{d['course_code']}** &nbsp; {title}  \n  _{due_str} UTC_")
        else:
            st.info("No assignments due in the next 14 days.")

        st.divider()

        st.subheader("Recent Announcements")
        if announcements:
            for announcement in announcements:
                posted = announcement["posted_at"].strftime("%b %d, %Y") if announcement["posted_at"] else "Unknown date"
                title = announcement["title"]
                if announcement["url"]:
                    title = f"[{title}]({announcement['url']})"
                st.markdown(f"- **{announcement['course_code']}** · {posted}  \n  {title}")
                if announcement["preview"]:
                    st.caption(announcement["preview"])
        else:
            st.info("No recent announcements found.")

        st.divider()

        st.subheader("Ask the Agent")
        st.caption("Ask anything about your grades and courses")

        if "messages" not in st.session_state:
            st.session_state.messages = []

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

        if prompt := st.chat_input("Ask about your grades..."):
            st.session_state.messages.append({"role": "user", "content": prompt, "tool_calls": []})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    answer, tool_calls = _run_agent(
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
                "role": "assistant",
                "content": answer,
                "tool_calls": tool_calls,
            })

    with acorn_tab:
        st.markdown(
            """
            <div style="text-align: center; padding: 3rem 1rem 4rem; color: #8a8f98;">
              <div style="font-size: 3rem; line-height: 1;">🔒</div>
              <div style="margin-top: 1rem; font-size: 1.5rem; font-weight: 600; color: #7a7f87;">
                ACORN Integration — Coming Soon
              </div>
              <div style="margin-top: 0.75rem; font-size: 1rem; color: #9aa0a8;">
                Import your academic history directly from ACORN. Currently in review.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


main()
