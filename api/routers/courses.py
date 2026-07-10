"""
api/routers/courses.py - Course, grade, scenario, weight, and token routes.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from api.dependencies import get_current_user
from api.integrations.quercus import QuercusAuthError
from api.services.grade_snapshot_cache import invalidate_grade_snapshot
from api.services.course_service import (
    CourseServiceError,
    QuercusError,
    get_dashboard_announcements,
    get_dashboard_course,
    get_course_grades,
    get_latest_course_announcement,
    get_course_scenarios,
    get_course_weights,
    list_current_term_courses,
    save_course_grade_overrides,
    delete_course_grade_override,
)
from api.integrations.grades_cache import GradesCacheError
from api.services.grades_snapshot_service import (
    GradesSnapshotServiceError,
    get_course_detail_snapshot,
    get_dashboard_snapshot,
    save_course_detail_snapshot,
    save_snapshot,
)
from api.auth.user_store import (
    UserStoreError,
    delete_quercus_token,
    get_quercus_token,
    save_quercus_token,
)
from api.services.manual_course_service import (
    ManualCourseServiceError,
    list_manual_courses,
    list_manual_deadlines,
    get_manual_course,
)
from api.integrations.grades_cache import get_grade_overrides

router = APIRouter(tags=["courses"])
logger = logging.getLogger(__name__)

# Per-user in-memory dashboard cache (full response, survives tab refreshes, cleared on restart)
_dashboard_cache: dict[str, dict] = {}

# Per-user per-course in-memory cache keyed by "{user_id}:{course_id}"
_course_grades_cache: dict[str, dict] = {}

# Per-user mapping from any canvas_id to all canvas_ids for the same UofT course.
# Populated when the dashboard is fetched; used by the grades route to merge
# data from sibling Canvas courses that share the same course code.
_canvas_id_groups: dict[str, list[int]] = {}


class QuercusTokenBody(BaseModel):
    token: str


class GradeOverrideItem(BaseModel):
    component_key: str
    manual_score: float
    manual_possible: float


class GradeOverridesBody(BaseModel):
    overrides: list[GradeOverrideItem]


def _evict_user_cache(user_id: str) -> None:
    """Drop all in-memory cached data for a user (called when their token changes)."""
    _dashboard_cache.pop(user_id, None)
    stale_keys = [k for k in _course_grades_cache if k.startswith(f"{user_id}:")]
    for k in stale_keys:
        del _course_grades_cache[k]
    stale_group_keys = [k for k in _canvas_id_groups if k.startswith(f"{user_id}:")]
    for k in stale_group_keys:
        del _canvas_id_groups[k]
    invalidate_grade_snapshot(user_id)


def _update_canvas_id_groups(user_id: str, courses: list[dict]) -> None:
    """Populate the canvas_id → sibling canvas_ids mapping from a dashboard course list.

    Also evicts in-memory course-grade cache entries for multi-ID courses so
    that a stale single-ID snapshot is not served before the merge runs.
    """
    for course in courses:
        canvas_ids = course.get("canvas_ids")
        if not canvas_ids or len(canvas_ids) <= 1:
            continue
        for cid in canvas_ids:
            key = f"{user_id}:{cid}"
            prev = _canvas_id_groups.get(key)
            _canvas_id_groups[key] = canvas_ids
            # If the known sibling set has grown, the cached grade data may
            # have been computed with fewer IDs — evict so the next request
            # does a live merged fetch instead of serving the stale snapshot.
            if set(prev or []) != set(canvas_ids):
                _course_grades_cache.pop(key, None)


def _token_debug_value(token: str | None) -> str:
    return "<present>" if token else "<missing>"


def _resolve_token(
    quercus_token: str | None,
    current_user: dict,
) -> str:
    """Return the caller-supplied token or fall back to the saved one."""
    if quercus_token:
        logger.info(
            "Resolved dashboard token from request user_id=%s token=%s",
            current_user.get("user_id"),
            _token_debug_value(quercus_token),
        )
        return quercus_token
    try:
        saved = get_quercus_token(current_user["user_id"])
    except UserStoreError as exc:
        logger.exception(
            "Failed to load saved Quercus token user_id=%s",
            current_user.get("user_id"),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to load saved Quercus token") from exc
    if not saved:
        logger.warning(
            "No saved Quercus token found user_id=%s",
            current_user.get("user_id"),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Quercus token provided and no saved token found. "
                   "Send the X-Quercus-Token header or save one via POST /api/quercus-token.",
        )
    logger.info(
        "Resolved dashboard token from saved Supabase token user_id=%s token=%s",
        current_user.get("user_id"),
        _token_debug_value(saved),
    )
    return saved


def _resolve_token_optional(
    quercus_token: str | None,
    current_user: dict,
) -> str | None:
    """Like _resolve_token but returns None instead of raising when no token exists."""
    if quercus_token:
        return quercus_token
    try:
        return get_quercus_token(current_user["user_id"])
    except UserStoreError:
        return None


# ---------------------------------------------------------------------------
# Quercus token management
# ---------------------------------------------------------------------------

@router.get("/quercus-token", dependencies=[Depends(get_current_user)])
def read_quercus_token(current_user: dict = Depends(get_current_user)):
    try:
        token = get_quercus_token(current_user["user_id"])
    except UserStoreError as exc:
        logger.exception("Failed to read saved Quercus token user_id=%s", current_user.get("user_id"))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to check token status") from exc
    if token is None:
        return {"exists": False}
    return {"exists": True}


@router.post("/quercus-token", dependencies=[Depends(get_current_user)])
def write_quercus_token(
    body: QuercusTokenBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        save_quercus_token(current_user["user_id"], body.token)
    except UserStoreError as exc:
        logger.exception("Failed to save Quercus token user_id=%s", current_user.get("user_id"))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to save Quercus token") from exc
    _evict_user_cache(current_user["user_id"])
    return {"status": "saved"}


@router.delete("/quercus-token", dependencies=[Depends(get_current_user)])
def remove_quercus_token(current_user: dict = Depends(get_current_user)):
    try:
        delete_quercus_token(current_user["user_id"])
    except UserStoreError as exc:
        logger.exception("Failed to delete Quercus token user_id=%s", current_user.get("user_id"))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to delete Quercus token") from exc
    _evict_user_cache(current_user["user_id"])
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Manual course dashboard helpers
# ---------------------------------------------------------------------------

def _build_manual_dashboard_card(course: dict, overrides: dict, deadlines: list[dict]) -> dict:
    """Build a dashboard-shaped dict from a manual_courses row."""
    from api.calculator.grades import GradeCalculator

    weights = course.get("weights") or {}
    components = []
    for name, weight in weights.items():
        override = overrides.get(name)
        if override:
            score = float(override.get("manual_score", 0))
            possible = float(override.get("manual_possible", 100))
            pct = (score / possible * 100) if possible else 0.0
            components.append({
                "name": name, "weight": float(weight), "status": "graded",
                "pct": round(pct, 2), "earned": score, "possible": possible,
            })
        else:
            components.append({
                "name": name, "weight": float(weight), "status": "ungraded",
                "pct": None, "earned": 0.0, "possible": 0.0,
            })

    total_weight = sum(c["weight"] for c in components)

    if total_weight > 0:
        projected_sum = sum((c["pct"] if c["status"] == "graded" else 100) * c["weight"] for c in components)
        current_grade = round(projected_sum / total_weight, 2)
        letter_grade = GradeCalculator._to_letter(current_grade)
    else:
        current_grade = 0.0
        letter_grade = "N/A"

    graded_weight = sum(c["weight"] for c in components if c["status"] == "graded")
    progress_pct = round(graded_weight / total_weight * 100, 1) if total_weight > 0 else 0.0
    risk_flag = "No breakdown" if not weights else ("On track" if current_grade >= 50 else "At risk")

    now_iso = datetime.now(timezone.utc).isoformat()
    fourteen_days = 14 * 24 * 3600
    course_deadlines = []
    for d in deadlines:
        if d.get("course_id") != course["id"]:
            continue
        course_deadlines.append({
            "course_code": course["course_code"],
            "name": d["name"],
            "due_at": d["due_at"],
            "manual_deadline_id": d["id"],
        })

    return {
        "id": course["id"],
        "canvas_ids": [],
        "course_code": course["course_code"],
        "name": course["course_name"],
        "term_name": course.get("term", ""),
        "current_grade": current_grade,
        "projected_grade": current_grade,
        "display_grade": current_grade,
        "letter_grade": letter_grade,
        "risk_flag": risk_flag,
        "progress_pct": progress_pct,
        "deadlines": course_deadlines,
        "source": "manual",
    }


def _get_manual_dashboard_cards(user_id: str) -> list[dict]:
    """Build dashboard cards for all manual courses of a user."""
    try:
        courses = list_manual_courses(user_id)
    except ManualCourseServiceError:
        logger.warning("Failed to load manual courses user_id=%s", user_id)
        return []

    if not courses:
        return []

    try:
        deadlines = list_manual_deadlines(user_id)
    except ManualCourseServiceError:
        deadlines = []

    cards = []
    for course in courses:
        try:
            overrides = get_grade_overrides(user_id, course["id"])
        except Exception:
            overrides = {}
        cards.append(_build_manual_dashboard_card(course, overrides, deadlines))
    return cards


# ---------------------------------------------------------------------------
# Course data routes  (token from query param or saved fallback)
# ---------------------------------------------------------------------------

@router.get("")
def list_courses(
    x_quercus_token: str | None = Header(default=None, alias="X-Quercus-Token"),
    current_user: dict = Depends(get_current_user),
):
    token = _resolve_token(x_quercus_token, current_user)
    try:
        return {"courses": list_current_term_courses(token)}
    except (CourseServiceError, QuercusError) as exc:
        logger.exception("Failed to list courses")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to load courses") from exc


async def _live_fetch_dashboard(token: str, user_id: str | None = None) -> tuple[list, list]:
    """Fetch courses and announcements from Quercus. Returns (dashboard, announcements)."""
    courses = await asyncio.to_thread(list_current_term_courses, token)
    tasks = [asyncio.to_thread(get_dashboard_course, token, course, user_id) for course in courses]
    dashboard = list(await asyncio.gather(*tasks))
    announcements = await asyncio.to_thread(get_dashboard_announcements, token, courses)
    return dashboard, announcements


async def _background_refresh_dashboard(token: str, user_id: str) -> None:
    try:
        dashboard, announcements = await _live_fetch_dashboard(token, user_id)
        term_name = next((c.get("term_name") for c in dashboard if c.get("term_name")), "")
        _dashboard_cache[user_id] = {
            "courses": dashboard,
            "announcements": announcements,
            "term_name": term_name,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        _update_canvas_id_groups(user_id, dashboard)
        try:
            await asyncio.to_thread(save_snapshot, user_id, dashboard, announcements)
        except GradesSnapshotServiceError as exc:
            logger.warning("Background snapshot save failed user_id=%s error=%s", user_id, exc)
        logger.info("Background dashboard refresh completed user_id=%s", user_id)
    except QuercusAuthError:
        logger.warning("Background dashboard refresh: token invalid/expired user_id=%s — deleting stored token", user_id)
        _evict_user_cache(user_id)
        try:
            delete_quercus_token(user_id)
        except UserStoreError:
            logger.warning("Failed to delete stored Quercus token during background refresh user_id=%s", user_id)
    except Exception:
        logger.exception("Background dashboard refresh failed user_id=%s", user_id)


@router.get("/dashboard")
async def dashboard_courses(
    force_refresh: bool = Query(default=False),
    x_quercus_token: str | None = Header(default=None, alias="X-Quercus-Token"),
    current_user: dict = Depends(get_current_user),
):
    token = _resolve_token_optional(x_quercus_token, current_user)
    user_id = current_user["user_id"]

    manual_cards = await asyncio.to_thread(_get_manual_dashboard_cards, user_id)

    try:
        all_manual_deadlines = list_manual_deadlines(user_id)
    except Exception:
        all_manual_deadlines = []
    orphan_deadlines = [d for d in all_manual_deadlines if d.get("course_id") is None]

    def _merge_manual(result: dict) -> dict:
        merged_courses = []
        for c in result.get("courses") or []:
            c_copy = {**c, "source": c.get("source", "quercus")}
            code = c_copy.get("course_code", "")
            matching = [d for d in orphan_deadlines if d.get("course_code") == code]
            if matching:
                c_copy["deadlines"] = list(c_copy.get("deadlines") or []) + [
                    {
                        "course_code": code,
                        "name": d["name"],
                        "due_at": d["due_at"],
                        "manual_deadline_id": d["id"],
                    }
                    for d in matching
                ]
            merged_courses.append(c_copy)
        return {**result, "courses": merged_courses + manual_cards}

    if not token:
        fetched_at = datetime.now(timezone.utc).isoformat()
        result = {
            "courses": manual_cards,
            "announcements": [],
            "term_name": "",
            "fetched_at": fetched_at,
        }
        _dashboard_cache[user_id] = result
        return result

    # Layer 1: in-memory cache — survives tab refreshes, instant
    if not force_refresh and user_id in _dashboard_cache:
        logger.info("Serving in-memory cached dashboard user_id=%s", user_id)
        asyncio.create_task(_background_refresh_dashboard(token, user_id))
        return _merge_manual(_dashboard_cache[user_id])

    # Layer 2: Supabase snapshot — survives server restarts, no Quercus calls needed
    if not force_refresh:
        try:
            snapshot = await asyncio.to_thread(get_dashboard_snapshot, user_id, 60 * 24)
        except Exception:
            logger.exception("Supabase snapshot read failed user_id=%s", user_id)
            snapshot = None
        if snapshot is not None:
            _dashboard_cache[user_id] = snapshot
            _update_canvas_id_groups(user_id, snapshot.get("courses") or [])
            logger.info("Serving Supabase snapshot user_id=%s fetched_at=%s", user_id, snapshot["fetched_at"])
            asyncio.create_task(_background_refresh_dashboard(token, user_id))
            return _merge_manual(snapshot)

    try:
        logger.info(
            "Starting live dashboard load user_id=%s token=%s force=%s",
            user_id,
            _token_debug_value(token),
            force_refresh,
        )
        dashboard, announcements = await _live_fetch_dashboard(token, user_id)
        fetched_at = datetime.now(timezone.utc).isoformat()
        term_name = next((c.get("term_name") for c in dashboard if c.get("term_name")), "")
        _dashboard_cache[user_id] = {
            "courses": dashboard,
            "announcements": announcements,
            "term_name": term_name,
            "fetched_at": fetched_at,
        }
        _update_canvas_id_groups(user_id, dashboard)
        try:
            await asyncio.to_thread(save_snapshot, user_id, dashboard, announcements)
        except GradesSnapshotServiceError as exc:
            logger.warning("Failed to persist grades snapshot user_id=%s error=%s", user_id, exc)
        logger.info(
            "Completed live dashboard load user_id=%s courses=%s announcements=%s",
            user_id,
            len(dashboard),
            len(announcements),
        )
        return _merge_manual(_dashboard_cache[user_id])
    except QuercusAuthError as exc:
        logger.warning("Dashboard load failed: token invalid/expired user_id=%s — deleting stored token", user_id)
        _evict_user_cache(user_id)
        try:
            delete_quercus_token(user_id)
        except UserStoreError:
            pass
        raise HTTPException(status_code=424, detail="quercus_token_invalid") from exc
    except (CourseServiceError, QuercusError) as exc:
        logger.exception(
            "Dashboard load failed user_id=%s token=%s",
            user_id,
            _token_debug_value(token),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to load dashboard data") from exc
    except Exception as exc:
        logger.exception(
            "Unexpected dashboard load failure user_id=%s token=%s error=%s",
            user_id,
            _token_debug_value(token),
            exc,
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected dashboard error") from exc


async def _background_refresh_course_grades(token: str, user_id: str, course_id: int) -> None:
    try:
        _siblings = _canvas_id_groups.get(f"{user_id}:{course_id}")
        _additional = [cid for cid in _siblings if cid != course_id] if _siblings else None
        data = await asyncio.to_thread(get_course_grades, token, course_id, user_id, _additional)
        _course_grades_cache[f"{user_id}:{course_id}"] = data
        await asyncio.to_thread(save_course_detail_snapshot, user_id, course_id, data)
        logger.info("Background course grades refresh completed user_id=%s course_id=%s", user_id, course_id)
    except QuercusAuthError:
        logger.warning("Background course grades refresh: token invalid/expired user_id=%s course_id=%s — deleting stored token", user_id, course_id)
        _evict_user_cache(user_id)
        try:
            delete_quercus_token(user_id)
        except UserStoreError:
            pass
    except Exception:
        logger.exception("Background course grades refresh failed user_id=%s course_id=%s", user_id, course_id)


def _build_manual_course_grades(user_id: str, course_id: int) -> dict:
    """Build a course-grades-shaped response for a manual course."""
    from api.calculator.grades import GradeCalculator

    course = get_manual_course(user_id, course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual course not found")

    weights = course.get("weights") or {}
    try:
        overrides = get_grade_overrides(user_id, course_id)
    except Exception:
        overrides = {}

    components = []
    for name, weight in weights.items():
        override = overrides.get(name)
        if override:
            score = float(override.get("manual_score", 0))
            possible = float(override.get("manual_possible", 100))
            pct = (score / possible * 100) if possible else 0.0
            components.append({
                "component_key": name,
                "name": name,
                "weight": float(weight),
                "status": "graded",
                "pct": round(pct, 2),
                "earned": score,
                "possible": possible,
                "is_manual": True,
                "manual_score": score,
                "manual_possible": possible,
                "source": "manual",
                "group_name": name,
            })
        else:
            components.append({
                "component_key": name,
                "name": name,
                "weight": float(weight),
                "status": "ungraded",
                "pct": None,
                "earned": 0.0,
                "possible": 0.0,
                "is_manual": False,
                "manual_score": None,
                "manual_possible": None,
                "source": "manual",
                "group_name": name,
            })

    graded = [c for c in components if c["status"] == "graded"]
    graded_weight = sum(c["weight"] for c in graded)
    total_weight = sum(c["weight"] for c in components)

    if graded_weight > 0:
        weighted_sum = sum(c["pct"] * c["weight"] for c in graded)
        weighted_grade = round(weighted_sum / graded_weight, 2)
        letter = GradeCalculator._to_letter(weighted_grade)
    else:
        weighted_grade = 0.0
        letter = "N/A"

    return {
        "course_id": course_id,
        "canvas_ids": [],
        "weights_source": "syllabus" if course.get("syllabus_source") else "manual",
        "weights": weights,
        "grade": {
            "weighted_grade": weighted_grade,
            "letter": letter,
            "graded_weight": graded_weight,
        },
        "component_model": {
            "reliable": bool(weights),
            "components": components,
            "assignments_by_component": {},
        },
        "live_components": [
            {
                "component_key": name,
                "name": name,
                "weight": float(w),
                "status": "ungraded",
                "pct": None,
                "earned": 0.0,
                "possible": 0.0,
                "is_manual": False,
                "manual_score": None,
                "manual_possible": None,
                "source": "manual",
                "group_name": name,
            }
            for name, w in weights.items()
        ],
        "overrides": {k: v for k, v in overrides.items()},
        "saved_grades": {},
        "new_grade_keys": [],
        "enrollment": None,
        "source": "manual",
    }


@router.get("/{course_id}/grades")
async def course_grades(
    course_id: int,
    force_refresh: bool = Query(default=False),
    x_quercus_token: str | None = Header(default=None, alias="X-Quercus-Token"),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]

    if course_id < 0:
        try:
            return _build_manual_course_grades(user_id, course_id)
        except ManualCourseServiceError as exc:
            logger.exception("Failed to load manual course grades course_id=%s", course_id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to load course grades") from exc

    token = _resolve_token(x_quercus_token, current_user)
    cache_key = f"{user_id}:{course_id}"
    _siblings = _canvas_id_groups.get(cache_key)
    _additional_ids = [cid for cid in _siblings if cid != course_id] if _siblings else None

    # Layer 1: in-memory
    if not force_refresh and cache_key in _course_grades_cache:
        asyncio.create_task(_background_refresh_course_grades(token, user_id, course_id))
        return _course_grades_cache[cache_key]

    # Layer 2: Supabase snapshot
    if not force_refresh:
        try:
            snapshot = await asyncio.to_thread(get_course_detail_snapshot, user_id, course_id, 60 * 24)
        except Exception:
            logger.exception("Course detail snapshot read failed user_id=%s course_id=%s", user_id, course_id)
            snapshot = None
        if snapshot is not None:
            # Validate that the snapshot was computed with the same set of canvas_ids
            # we now know about. A snapshot saved before the merge fix (or before the
            # dashboard revealed a sibling ID) would show no grades — skip it and
            # fall through to a live merged fetch.
            expected_ids = set([course_id] + (_additional_ids or []))
            snapshot_ids = set(snapshot.get("canvas_ids") or [course_id])
            if snapshot_ids == expected_ids:
                _course_grades_cache[cache_key] = snapshot
                logger.info("Serving Supabase course detail user_id=%s course_id=%s", user_id, course_id)
                asyncio.create_task(_background_refresh_course_grades(token, user_id, course_id))
                return snapshot
            logger.info(
                "Discarding stale course detail snapshot (ids %s != expected %s) user_id=%s course_id=%s",
                snapshot_ids, expected_ids, user_id, course_id,
            )

    # Layer 3: live fetch
    try:
        data = await asyncio.to_thread(get_course_grades, token, course_id, user_id, _additional_ids)
        _course_grades_cache[cache_key] = data
        try:
            await asyncio.to_thread(save_course_detail_snapshot, user_id, course_id, data)
        except GradesSnapshotServiceError as exc:
            logger.warning("Failed to save course detail snapshot user_id=%s course_id=%s error=%s", user_id, course_id, exc)
        return data
    except QuercusAuthError as exc:
        logger.warning("Course grades load failed: token invalid/expired user_id=%s course_id=%s", user_id, course_id)
        _evict_user_cache(user_id)
        try:
            delete_quercus_token(user_id)
        except UserStoreError:
            pass
        raise HTTPException(status_code=424, detail="quercus_token_invalid") from exc
    except (CourseServiceError, QuercusError, GradesCacheError) as exc:
        logger.exception("Failed to load course grades course_id=%s", course_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to load course grades") from exc


@router.post("/{course_id}/grade-overrides")
def write_course_grade_overrides(
    course_id: int,
    body: GradeOverridesBody,
    x_quercus_token: str | None = Header(default=None, alias="X-Quercus-Token"),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]

    if course_id < 0:
        from api.integrations.grades_cache import save_grade_override
        for override in body.overrides:
            save_grade_override(
                user_id, course_id,
                override.component_key, override.manual_score, override.manual_possible,
            )
        data = _build_manual_course_grades(user_id, course_id)
        cache_key = f"{user_id}:{course_id}"
        _course_grades_cache[cache_key] = data
        _dashboard_cache.pop(user_id, None)
        return data

    token = _resolve_token(x_quercus_token, current_user)
    cache_key = f"{user_id}:{course_id}"
    _siblings = _canvas_id_groups.get(cache_key)
    _additional_ids = [cid for cid in _siblings if cid != course_id] if _siblings else None
    try:
        data = save_course_grade_overrides(
            token,
            user_id,
            course_id,
            [override.model_dump() for override in body.overrides],
            cached_snapshot=_course_grades_cache.get(cache_key),
            additional_canvas_ids=_additional_ids,
        )
        _course_grades_cache[cache_key] = data
        _dashboard_cache.pop(user_id, None)
        try:
            save_course_detail_snapshot(user_id, course_id, data)
        except GradesSnapshotServiceError as exc:
            logger.warning("Failed to persist grade override snapshot user_id=%s course_id=%s error=%s", user_id, course_id, exc)
        return data
    except (CourseServiceError, QuercusError, GradesCacheError) as exc:
        logger.exception("Failed to save grade overrides course_id=%s", course_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to save grade overrides") from exc


@router.delete("/{course_id}/grade-overrides/{component_key}")
def remove_course_grade_override(
    course_id: int,
    component_key: str,
    x_quercus_token: str | None = Header(default=None, alias="X-Quercus-Token"),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]

    if course_id < 0:
        from api.integrations.grades_cache import delete_grade_override
        delete_grade_override(user_id, course_id, component_key)
        data = _build_manual_course_grades(user_id, course_id)
        cache_key = f"{user_id}:{course_id}"
        _course_grades_cache[cache_key] = data
        _dashboard_cache.pop(user_id, None)
        return data

    token = _resolve_token(x_quercus_token, current_user)
    cache_key = f"{user_id}:{course_id}"
    _siblings = _canvas_id_groups.get(cache_key)
    _additional_ids = [cid for cid in _siblings if cid != course_id] if _siblings else None
    try:
        cached = _course_grades_cache.get(cache_key)
        data = delete_course_grade_override(token, user_id, course_id, component_key, cached, _additional_ids)
        _course_grades_cache[cache_key] = data
        _dashboard_cache.pop(user_id, None)
        try:
            save_course_detail_snapshot(user_id, course_id, data)
        except GradesSnapshotServiceError as exc:
            logger.warning("Failed to persist delete-override snapshot user_id=%s course_id=%s error=%s", user_id, course_id, exc)
        return data
    except (CourseServiceError, QuercusError, GradesCacheError) as exc:
        logger.exception("Failed to delete grade override course_id=%s", course_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to delete grade override") from exc


@router.get("/{course_id}/announcements/latest")
def latest_course_announcement(
    course_id: int,
    x_quercus_token: str | None = Header(default=None, alias="X-Quercus-Token"),
    current_user: dict = Depends(get_current_user),
):
    token = _resolve_token(x_quercus_token, current_user)
    try:
        return get_latest_course_announcement(token, course_id)
    except (CourseServiceError, QuercusError) as exc:
        logger.exception("Failed to load announcement course_id=%s", course_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to load announcement") from exc


@router.get("/{course_id}/scenarios")
def course_scenarios(
    course_id: int,
    x_quercus_token: str | None = Header(default=None, alias="X-Quercus-Token"),
    current_user: dict = Depends(get_current_user),
):
    token = _resolve_token(x_quercus_token, current_user)
    try:
        return get_course_scenarios(token, course_id)
    except (CourseServiceError, QuercusError) as exc:
        logger.exception("Failed to load scenarios course_id=%s", course_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to load grade scenarios") from exc


@router.get("/{course_id}/weights")
def course_weights(
    course_id: int,
    x_quercus_token: str | None = Header(default=None, alias="X-Quercus-Token"),
    current_user: dict = Depends(get_current_user),
):
    token = _resolve_token(x_quercus_token, current_user)
    try:
        return get_course_weights(token, course_id)
    except (CourseServiceError, QuercusError) as exc:
        logger.exception("Failed to load weights course_id=%s", course_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to load course weights") from exc
