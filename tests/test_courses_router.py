"""
tests/test_courses_router.py — tests for api/routers/courses.py route handlers.

Since starlette 1.0.0 + fastapi 0.103.2 middleware is incompatible with
TestClient HTTP transport, handlers are called directly as Python
functions/coroutines with mocked dependencies.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException


def _user(user_id="u-test"):
    return {
        "user_id": user_id,
        "email": "test@example.com",
        "name": "Test User",
        "google_id": "g-test",
    }


# ── Quercus token CRUD ────────────────────────────────────────────────────────

class TestReadQuercusToken:
    def test_returns_token_when_found(self):
        from api.routers.courses import read_quercus_token
        with patch("api.routers.courses.get_quercus_token", return_value="tok-abc"):
            result = read_quercus_token(current_user=_user())
        assert result == {"token": "tok-abc"}

    def test_raises_404_when_token_missing(self):
        from api.routers.courses import read_quercus_token
        with patch("api.routers.courses.get_quercus_token", return_value=None):
            with pytest.raises(HTTPException) as exc:
                read_quercus_token(current_user=_user())
        assert exc.value.status_code == 404

    def test_raises_400_on_user_store_error(self):
        from api.routers.courses import read_quercus_token
        from auth.user_store import UserStoreError
        with patch("api.routers.courses.get_quercus_token", side_effect=UserStoreError("db fail")):
            with pytest.raises(HTTPException) as exc:
                read_quercus_token(current_user=_user())
        assert exc.value.status_code == 400


class TestWriteQuercusToken:
    def test_saves_token_and_returns_saved(self):
        from api.routers.courses import write_quercus_token, QuercusTokenBody
        body = QuercusTokenBody(token="my-token")
        with patch("api.routers.courses.save_quercus_token"), \
             patch("api.routers.courses._evict_user_cache"):
            result = write_quercus_token(body=body, current_user=_user())
        assert result == {"status": "saved"}

    def test_raises_400_on_save_error(self):
        from api.routers.courses import write_quercus_token, QuercusTokenBody
        from auth.user_store import UserStoreError
        body = QuercusTokenBody(token="tok")
        with patch("api.routers.courses.save_quercus_token", side_effect=UserStoreError("fail")):
            with pytest.raises(HTTPException) as exc:
                write_quercus_token(body=body, current_user=_user())
        assert exc.value.status_code == 400


class TestRemoveQuercusToken:
    def test_deletes_token_and_returns_deleted(self):
        from api.routers.courses import remove_quercus_token
        with patch("api.routers.courses.delete_quercus_token"), \
             patch("api.routers.courses._evict_user_cache"):
            result = remove_quercus_token(current_user=_user())
        assert result == {"status": "deleted"}

    def test_raises_400_on_delete_error(self):
        from api.routers.courses import remove_quercus_token
        from auth.user_store import UserStoreError
        with patch("api.routers.courses.delete_quercus_token", side_effect=UserStoreError("fail")):
            with pytest.raises(HTTPException) as exc:
                remove_quercus_token(current_user=_user())
        assert exc.value.status_code == 400


# ── list_courses ──────────────────────────────────────────────────────────────

class TestListCourses:
    def test_returns_courses_list(self):
        from api.routers.courses import list_courses
        fake_courses = [{"id": 1, "name": "Intro CS"}]
        with patch("api.routers.courses._resolve_token", return_value="tok"), \
             patch("api.routers.courses.list_current_term_courses", return_value=fake_courses):
            result = list_courses(quercus_token="tok", current_user=_user())
        assert result == {"courses": fake_courses}

    def test_raises_400_on_course_service_error(self):
        from api.routers.courses import list_courses
        from api.services.course_service import CourseServiceError
        with patch("api.routers.courses._resolve_token", return_value="tok"), \
             patch("api.routers.courses.list_current_term_courses", side_effect=CourseServiceError("no tok")):
            with pytest.raises(HTTPException) as exc:
                list_courses(quercus_token=None, current_user=_user())
        assert exc.value.status_code == 400


# ── dashboard_courses ─────────────────────────────────────────────────────────

class TestDashboardCourses:
    def test_in_memory_cache_hit(self):
        """When _dashboard_cache has data for the user, return it immediately."""
        import api.routers.courses as mod
        user_id = "u-cached"
        cached_data = {
            "courses": [{"id": 1}],
            "announcements": [],
            "term_name": "Fall 2024",
            "fetched_at": "2024-11-01T00:00:00+00:00",
        }
        mod._dashboard_cache[user_id] = cached_data

        async def run():
            with patch("api.routers.courses._resolve_token", return_value="tok"), \
                 patch("api.routers.courses.asyncio.create_task"):  # suppress background refresh
                return await mod.dashboard_courses(
                    force_refresh=False,
                    quercus_token="tok",
                    current_user={"user_id": user_id, **{k: v for k, v in _user().items() if k != "user_id"}},
                )

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result["courses"] == [{"id": 1}]
        del mod._dashboard_cache[user_id]

    def test_force_refresh_bypasses_cache(self):
        """force_refresh=True skips both cache tiers and does a live fetch."""
        import api.routers.courses as mod
        fake_dashboard = [{"id": 1, "name": "CS", "term_name": "Fall 2024"}]
        fake_announcements = []

        async def run():
            with patch("api.routers.courses._resolve_token", return_value="tok"), \
                 patch("api.routers.courses._live_fetch_dashboard",
                       return_value=(fake_dashboard, fake_announcements)), \
                 patch("api.routers.courses.save_snapshot"):
                return await mod.dashboard_courses(
                    force_refresh=True,
                    quercus_token="tok",
                    current_user=_user(),
                )

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result["courses"] == fake_dashboard

    def test_raises_424_on_quercus_auth_error(self):
        """QuercusAuthError during live fetch → HTTP 424."""
        import api.routers.courses as mod
        from integrations.quercus import QuercusAuthError

        async def run():
            with patch("api.routers.courses._resolve_token", return_value="tok"), \
                 patch("api.routers.courses.get_dashboard_snapshot", return_value=None), \
                 patch("api.routers.courses._live_fetch_dashboard",
                       side_effect=QuercusAuthError("invalid token")):
                return await mod.dashboard_courses(
                    force_refresh=True,
                    quercus_token="tok",
                    current_user=_user(),
                )

        with pytest.raises(HTTPException) as exc:
            asyncio.get_event_loop().run_until_complete(run())
        assert exc.value.status_code == 424

    def test_supabase_snapshot_returned_when_no_mem_cache(self):
        """Layer 2: Supabase snapshot returned if in-memory cache misses."""
        import api.routers.courses as mod
        snapshot = {
            "courses": [{"id": 99}],
            "announcements": [],
            "term_name": "Winter 2025",
            "fetched_at": "2025-01-01T00:00:00+00:00",
        }

        async def run():
            with patch("api.routers.courses._resolve_token", return_value="tok"), \
                 patch("api.routers.courses.get_dashboard_snapshot", return_value=snapshot), \
                 patch("api.routers.courses.asyncio.create_task"):
                return await mod.dashboard_courses(
                    force_refresh=False,
                    quercus_token="tok",
                    current_user={"user_id": "u-fresh", **{k: v for k, v in _user().items() if k != "user_id"}},
                )

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result["courses"] == [{"id": 99}]

    def test_cached_dashboard_kicks_off_background_refresh(self):
        import api.routers.courses as mod
        user_id = "u-bg"
        mod._dashboard_cache[user_id] = {
            "courses": [{"id": 1}],
            "announcements": [],
            "term_name": "Fall 2024",
            "fetched_at": "2024-11-01T00:00:00+00:00",
        }

        async def run():
            with patch("api.routers.courses._resolve_token", return_value="tok"), \
                 patch("api.routers.courses.asyncio.create_task") as mock_task:
                result = await mod.dashboard_courses(False, "tok", {"user_id": user_id})
            assert mock_task.called
            return result

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result["courses"] == [{"id": 1}]
        del mod._dashboard_cache[user_id]


class TestBackgroundRefreshDashboard:
    def test_background_refresh_completes_and_persists(self):
        import api.routers.courses as mod

        async def run():
            with patch("api.routers.courses._live_fetch_dashboard", return_value=([{"id": 1, "term_name": "Fall 2024"}], [])), \
                 patch("api.routers.courses.save_snapshot"):
                await mod._background_refresh_dashboard("tok", "u1")

        asyncio.get_event_loop().run_until_complete(run())
        assert mod._dashboard_cache["u1"]["courses"] == [{"id": 1, "term_name": "Fall 2024"}]
        del mod._dashboard_cache["u1"]

    def test_background_refresh_failures_are_swallowed(self):
        import api.routers.courses as mod

        async def run():
            with patch("api.routers.courses._live_fetch_dashboard", side_effect=RuntimeError("boom")):
                await mod._background_refresh_dashboard("tok", "u-fail")

        asyncio.get_event_loop().run_until_complete(run())


# ── course_grades ─────────────────────────────────────────────────────────────

class TestCourseGrades:
    def test_in_memory_cache_hit(self):
        import api.routers.courses as mod
        user_id = "u-grades"
        course_id = 2001
        cached = {"course_id": course_id, "grade": {"weighted_grade": 82.0}}
        mod._course_grades_cache[f"{user_id}:{course_id}"] = cached

        async def run():
            with patch("api.routers.courses._resolve_token", return_value="tok"), \
                 patch("api.routers.courses.asyncio.create_task"):
                return await mod.course_grades(
                    course_id=course_id,
                    force_refresh=False,
                    quercus_token="tok",
                    current_user={"user_id": user_id, **{k: v for k, v in _user().items() if k != "user_id"}},
                )

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result["course_id"] == course_id
        del mod._course_grades_cache[f"{user_id}:{course_id}"]

    def test_live_fetch_on_cache_miss(self):
        import api.routers.courses as mod
        fake_data = {"course_id": 3001, "grade": {"weighted_grade": 75.0}, "components": []}

        async def run():
            with patch("api.routers.courses._resolve_token", return_value="tok"), \
                 patch("api.routers.courses.get_course_detail_snapshot", return_value=None), \
                 patch("api.routers.courses.get_course_grades", return_value=fake_data), \
                 patch("api.routers.courses.save_course_detail_snapshot"):
                return await mod.course_grades(
                    course_id=3001,
                    force_refresh=False,
                    quercus_token="tok",
                    current_user=_user(),
                )

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result["course_id"] == 3001


# ── course_scenarios ──────────────────────────────────────────────────────────

class TestCourseScenarios:
    def test_returns_scenarios(self):
        from api.routers.courses import course_scenarios
        fake = {"course_id": 1001, "scenarios": {}}
        with patch("api.routers.courses._resolve_token", return_value="tok"), \
             patch("api.routers.courses.get_course_scenarios", return_value=fake):
            result = course_scenarios(
                course_id=1001,
                quercus_token="tok",
                current_user=_user(),
            )
        assert result == fake

    def test_raises_400_on_error(self):
        from api.routers.courses import course_scenarios
        from api.services.course_service import CourseServiceError
        with patch("api.routers.courses._resolve_token", return_value="tok"), \
             patch("api.routers.courses.get_course_scenarios",
                   side_effect=CourseServiceError("no weights")):
            with pytest.raises(HTTPException) as exc:
                course_scenarios(course_id=1001, quercus_token="tok", current_user=_user())
        assert exc.value.status_code == 400

    def test_returns_impossible_scenario_payload(self):
        from api.routers.courses import course_scenarios
        fake = {"course_id": 1001, "scenarios": {"A+": {"status": "impossible", "needed": 140.0}}}
        with patch("api.routers.courses._resolve_token", return_value="tok"), \
             patch("api.routers.courses.get_course_scenarios", return_value=fake):
            result = course_scenarios(course_id=1001, quercus_token="tok", current_user=_user())
        assert result["scenarios"]["A+"]["status"] == "impossible"


# ── course_weights ────────────────────────────────────────────────────────────

class TestCourseWeights:
    def test_returns_weights(self):
        from api.routers.courses import course_weights
        fake = {"course_id": 1001, "weights": {"Midterm": 40.0}}
        with patch("api.routers.courses._resolve_token", return_value="tok"), \
             patch("api.routers.courses.get_course_weights", return_value=fake):
            result = course_weights(course_id=1001, quercus_token="tok", current_user=_user())
        assert result == fake

    def test_returns_none_weights_gracefully(self):
        from api.routers.courses import course_weights
        fake = {"course_id": 1001, "weights_source": None, "weights": {}}
        with patch("api.routers.courses._resolve_token", return_value="tok"), \
             patch("api.routers.courses.get_course_weights", return_value=fake):
            result = course_weights(course_id=1001, quercus_token="tok", current_user=_user())
        assert result["weights"] == {}


class TestQuercusTokenRoundTrip:
    def test_write_then_read_round_trip_with_saved_value(self):
        from api.routers.courses import write_quercus_token, read_quercus_token, QuercusTokenBody
        store = {}

        def fake_save(user_id, token):
            store[user_id] = token

        def fake_get(user_id):
            return store.get(user_id)

        with patch("api.routers.courses.save_quercus_token", side_effect=fake_save), \
             patch("api.routers.courses.get_quercus_token", side_effect=fake_get), \
             patch("api.routers.courses._evict_user_cache"):
            assert write_quercus_token(QuercusTokenBody(token="encrypted-roundtrip"), _user()) == {"status": "saved"}
            result = read_quercus_token(_user())
        assert result == {"token": "encrypted-roundtrip"}

    def test_delete_when_no_token_exists_is_still_graceful(self):
        from api.routers.courses import remove_quercus_token
        with patch("api.routers.courses.delete_quercus_token", return_value=None), \
             patch("api.routers.courses._evict_user_cache"):
            result = remove_quercus_token(current_user=_user())
        assert result == {"status": "deleted"}


# ── _resolve_token ────────────────────────────────────────────────────────────

class TestResolveToken:
    def test_supplied_token_wins(self):
        from api.routers.courses import _resolve_token
        with patch("api.routers.courses.get_quercus_token", return_value="saved"):
            result = _resolve_token("supplied", {"user_id": "u1"})
        assert result == "supplied"

    def test_falls_back_to_saved(self):
        from api.routers.courses import _resolve_token
        with patch("api.routers.courses.get_quercus_token", return_value="saved"):
            result = _resolve_token(None, {"user_id": "u1"})
        assert result == "saved"

    def test_raises_400_when_no_saved_token(self):
        from api.routers.courses import _resolve_token
        with patch("api.routers.courses.get_quercus_token", return_value=None):
            with pytest.raises(HTTPException) as exc:
                _resolve_token(None, {"user_id": "u1"})
        assert exc.value.status_code == 400


# ── _evict_user_cache ─────────────────────────────────────────────────────────

# ── write_course_grade_overrides ──────────────────────────────────────────────

class TestWriteCourseGradeOverrides:
    def test_saves_overrides_and_returns_data(self):
        from api.routers.courses import write_course_grade_overrides, GradeOverridesBody, GradeOverrideItem
        body = GradeOverridesBody(overrides=[
            GradeOverrideItem(component_key="midterm", manual_score=80.0, manual_possible=100.0)
        ])
        fake_data = {"course_id": 1001, "grade": {"weighted_grade": 80.0}, "components": []}
        with patch("api.routers.courses._resolve_token", return_value="tok"), \
             patch("api.routers.courses.save_course_grade_overrides", return_value=fake_data), \
             patch("api.routers.courses.save_course_detail_snapshot"):
            result = write_course_grade_overrides(course_id=1001, body=body, quercus_token="tok", current_user=_user())
        assert result["course_id"] == 1001

    def test_raises_400_on_error(self):
        from api.routers.courses import write_course_grade_overrides, GradeOverridesBody
        from api.services.course_service import CourseServiceError
        body = GradeOverridesBody(overrides=[])
        with patch("api.routers.courses._resolve_token", return_value="tok"), \
             patch("api.routers.courses.save_course_grade_overrides",
                   side_effect=CourseServiceError("fail")):
            with pytest.raises(HTTPException) as exc:
                write_course_grade_overrides(course_id=1001, body=body, quercus_token="tok", current_user=_user())
        assert exc.value.status_code == 400


# ── remove_course_grade_override ──────────────────────────────────────────────

class TestRemoveCourseGradeOverride:
    def test_deletes_override_and_returns_data(self):
        from api.routers.courses import remove_course_grade_override
        fake_data = {"course_id": 1001, "grade": {"weighted_grade": 85.0}, "components": []}
        with patch("api.routers.courses._resolve_token", return_value="tok"), \
             patch("api.routers.courses.delete_course_grade_override", return_value=fake_data), \
             patch("api.routers.courses.save_course_detail_snapshot"):
            result = remove_course_grade_override(
                course_id=1001, component_key="midterm", quercus_token="tok", current_user=_user()
            )
        assert result["course_id"] == 1001

    def test_raises_400_on_error(self):
        from api.routers.courses import remove_course_grade_override
        from api.services.course_service import CourseServiceError
        with patch("api.routers.courses._resolve_token", return_value="tok"), \
             patch("api.routers.courses.delete_course_grade_override",
                   side_effect=CourseServiceError("not found")):
            with pytest.raises(HTTPException) as exc:
                remove_course_grade_override(
                    course_id=1001, component_key="midterm", quercus_token="tok", current_user=_user()
                )
        assert exc.value.status_code == 400


# ── latest_course_announcement ────────────────────────────────────────────────

class TestLatestCourseAnnouncement:
    def test_returns_announcement(self):
        from api.routers.courses import latest_course_announcement
        fake = {"course_id": 1001, "title": "Midterm reminder", "body_html": "<p>...</p>"}
        with patch("api.routers.courses._resolve_token", return_value="tok"), \
             patch("api.routers.courses.get_latest_course_announcement", return_value=fake):
            result = latest_course_announcement(course_id=1001, quercus_token="tok", current_user=_user())
        assert result["course_id"] == 1001

    def test_raises_400_when_no_announcement(self):
        from api.routers.courses import latest_course_announcement
        from api.services.course_service import CourseServiceError
        with patch("api.routers.courses._resolve_token", return_value="tok"), \
             patch("api.routers.courses.get_latest_course_announcement",
                   side_effect=CourseServiceError("no announcement")):
            with pytest.raises(HTTPException) as exc:
                latest_course_announcement(course_id=1001, quercus_token="tok", current_user=_user())
        assert exc.value.status_code == 400


# ── _evict_user_cache ─────────────────────────────────────────────────────────

class TestEvictUserCache:
    def test_clears_dashboard_and_grades_cache(self):
        import api.routers.courses as mod
        mod._dashboard_cache["u-evict"] = {"courses": []}
        mod._course_grades_cache["u-evict:1001"] = {"course_id": 1001}
        mod._course_grades_cache["u-evict:1002"] = {"course_id": 1002}
        mod._course_grades_cache["other-user:1003"] = {"course_id": 1003}

        with patch("api.routers.courses.invalidate_grade_snapshot"):
            mod._evict_user_cache("u-evict")

        assert "u-evict" not in mod._dashboard_cache
        assert "u-evict:1001" not in mod._course_grades_cache
        assert "u-evict:1002" not in mod._course_grades_cache
        assert "other-user:1003" in mod._course_grades_cache


class TestResolveTokenAdditional:
    def test_raises_400_when_user_store_lookup_fails(self):
        from api.routers.courses import _resolve_token
        from auth.user_store import UserStoreError
        with patch("api.routers.courses.get_quercus_token", side_effect=UserStoreError("db down")):
            with pytest.raises(HTTPException) as exc:
                _resolve_token(None, {"user_id": "u1"})
        assert exc.value.status_code == 400


class TestTokenDebugValue:
    def test_formats_missing_short_and_long_tokens(self):
        from api.routers.courses import _token_debug_value
        assert _token_debug_value(None) == "<missing>"
        assert _token_debug_value("shorttok") == "shorttok"
        assert _token_debug_value("abcdefghijklmnopqrstuvwxyz") == "abcdef...wxyz (len=26)"


class TestLiveFetchDashboardAdditional:
    def test_fetches_courses_then_course_cards_and_announcements(self):
        import api.routers.courses as mod

        async def run():
            with patch("api.routers.courses.list_current_term_courses", return_value=[{"id": 1}, {"id": 2}]), \
                 patch("api.routers.courses.get_dashboard_course", side_effect=[{"id": 1, "term_name": "Fall"}, {"id": 2}]), \
                 patch("api.routers.courses.get_dashboard_announcements", return_value=[{"id": 10}]):
                return await mod._live_fetch_dashboard("tok")

        dashboard, announcements = asyncio.get_event_loop().run_until_complete(run())
        assert [row["id"] for row in dashboard] == [1, 2]
        assert announcements == [{"id": 10}]


class TestDashboardCoursesAdditional:
    def test_snapshot_read_failure_falls_back_to_live_fetch(self):
        import api.routers.courses as mod
        fake_dashboard = [{"id": 1, "term_name": "Winter 2025"}]

        async def run():
            with patch("api.routers.courses._resolve_token", return_value="tok"), \
                 patch("api.routers.courses.get_dashboard_snapshot", side_effect=RuntimeError("snapshot down")), \
                 patch("api.routers.courses._live_fetch_dashboard", return_value=(fake_dashboard, [])), \
                 patch("api.routers.courses.save_snapshot"):
                return await mod.dashboard_courses(False, "tok", {"user_id": "u-fallback"})

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result["term_name"] == "Winter 2025"
        del mod._dashboard_cache["u-fallback"]

    def test_raises_400_on_course_service_failure(self):
        import api.routers.courses as mod
        from api.services.course_service import CourseServiceError

        async def run():
            with patch("api.routers.courses._resolve_token", return_value="tok"), \
                 patch("api.routers.courses._live_fetch_dashboard", side_effect=CourseServiceError("load failed")):
                return await mod.dashboard_courses(True, "tok", _user())

        with pytest.raises(HTTPException) as exc:
            asyncio.get_event_loop().run_until_complete(run())
        assert exc.value.status_code == 400

    def test_raises_500_on_unexpected_failure(self):
        import api.routers.courses as mod

        async def run():
            with patch("api.routers.courses._resolve_token", return_value="tok"), \
                 patch("api.routers.courses._live_fetch_dashboard", side_effect=RuntimeError("boom")):
                return await mod.dashboard_courses(True, "tok", _user())

        with pytest.raises(HTTPException) as exc:
            asyncio.get_event_loop().run_until_complete(run())
        assert exc.value.status_code == 500

    def test_live_fetch_snapshot_persist_failure_is_swallowed(self):
        import api.routers.courses as mod
        from api.services.grades_snapshot_service import GradesSnapshotServiceError
        fake_dashboard = [{"id": 2, "term_name": "Summer 2025"}]

        async def run():
            with patch("api.routers.courses._resolve_token", return_value="tok"), \
                 patch("api.routers.courses._live_fetch_dashboard", return_value=(fake_dashboard, [])), \
                 patch("api.routers.courses.save_snapshot", side_effect=GradesSnapshotServiceError("write fail")):
                return await mod.dashboard_courses(True, "tok", {"user_id": "u-persist"})

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result["courses"] == fake_dashboard  # pragma: no cover
        del mod._dashboard_cache["u-persist"]  # pragma: no cover


class TestBackgroundRefreshDashboardAdditional:
    def test_marks_auth_error_on_cached_entry(self):
        import api.routers.courses as mod
        from integrations.quercus import QuercusAuthError

        mod._dashboard_cache["u-auth"] = {"courses": []}

        async def run():
            with patch("api.routers.courses._live_fetch_dashboard", side_effect=QuercusAuthError("expired")):
                await mod._background_refresh_dashboard("tok", "u-auth")

        asyncio.get_event_loop().run_until_complete(run())
        assert mod._dashboard_cache["u-auth"]["auth_error"] == "quercus_token_invalid"
        del mod._dashboard_cache["u-auth"]

    def test_snapshot_save_failure_is_swallowed(self):
        import api.routers.courses as mod
        from api.services.grades_snapshot_service import GradesSnapshotServiceError

        async def run():
            with patch("api.routers.courses._live_fetch_dashboard", return_value=([{"id": 1}], [])), \
                 patch("api.routers.courses.save_snapshot", side_effect=GradesSnapshotServiceError("save fail")):
                await mod._background_refresh_dashboard("tok", "u-snapshot")

        asyncio.get_event_loop().run_until_complete(run())
        assert mod._dashboard_cache["u-snapshot"]["courses"] == [{"id": 1}]  # pragma: no cover
        del mod._dashboard_cache["u-snapshot"]  # pragma: no cover


class TestCourseGradesAdditional:
    def test_snapshot_hit_returns_cached_detail_and_refreshes_in_background(self):
        import api.routers.courses as mod
        snapshot = {"course_id": 4001, "grade": {"weighted_grade": 88.0}, "components": []}

        async def run():
            with patch("api.routers.courses._resolve_token", return_value="tok"), \
                 patch("api.routers.courses.get_course_detail_snapshot", return_value=snapshot), \
                 patch("api.routers.courses.asyncio.create_task") as mock_task:
                result = await mod.course_grades(4001, False, "tok", {"user_id": "u-snap"})
            assert mock_task.called
            return result

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result["course_id"] == 4001

    def test_snapshot_read_failure_falls_back_to_live_fetch(self):
        import api.routers.courses as mod
        fake_data = {"course_id": 5001, "grade": {"weighted_grade": 70.0}, "components": []}

        async def run():
            with patch("api.routers.courses._resolve_token", return_value="tok"), \
                 patch("api.routers.courses.get_course_detail_snapshot", side_effect=RuntimeError("snapshot down")), \
                 patch("api.routers.courses.get_course_grades", return_value=fake_data), \
                 patch("api.routers.courses.save_course_detail_snapshot"):
                return await mod.course_grades(5001, False, "tok", _user())

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result["grade"]["weighted_grade"] == 70.0

    def test_snapshot_save_failure_after_live_fetch_is_swallowed(self):
        import api.routers.courses as mod
        from api.services.grades_snapshot_service import GradesSnapshotServiceError
        fake_data = {"course_id": 6001, "grade": {"weighted_grade": 71.0}, "components": []}

        async def run():
            with patch("api.routers.courses._resolve_token", return_value="tok"), \
                 patch("api.routers.courses.get_course_detail_snapshot", return_value=None), \
                 patch("api.routers.courses.get_course_grades", return_value=fake_data), \
                 patch("api.routers.courses.save_course_detail_snapshot", side_effect=GradesSnapshotServiceError("write fail")):
                return await mod.course_grades(6001, False, "tok", _user())

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result["course_id"] == 6001  # pragma: no cover

    def test_raises_400_on_course_grades_error(self):
        import api.routers.courses as mod
        from api.services.course_service import CourseServiceError

        async def run():
            with patch("api.routers.courses._resolve_token", return_value="tok"), \
                 patch("api.routers.courses.get_course_detail_snapshot", return_value=None), \
                 patch("api.routers.courses.get_course_grades", side_effect=CourseServiceError("bad data")):
                return await mod.course_grades(7001, False, "tok", _user())

        with pytest.raises(HTTPException) as exc:
            asyncio.get_event_loop().run_until_complete(run())
        assert exc.value.status_code == 400


class TestBackgroundRefreshCourseGrades:
    def test_updates_cache(self):
        import api.routers.courses as mod

        async def run():
            with patch("api.routers.courses.get_course_grades", return_value={"course_id": 12}), \
                 patch("api.routers.courses.save_course_detail_snapshot"):
                await mod._background_refresh_course_grades("tok", "u-course", 12)

        asyncio.get_event_loop().run_until_complete(run())
        assert mod._course_grades_cache["u-course:12"]["course_id"] == 12
        del mod._course_grades_cache["u-course:12"]

    def test_failure_is_swallowed(self):
        import api.routers.courses as mod

        async def run():
            with patch("api.routers.courses.get_course_grades", side_effect=RuntimeError("boom")):
                await mod._background_refresh_course_grades("tok", "u-course", 13)

        asyncio.get_event_loop().run_until_complete(run())


class TestWriteCourseGradeOverridesAdditional:
    def test_snapshot_persist_failure_is_swallowed(self):
        from api.routers.courses import write_course_grade_overrides, GradeOverridesBody, GradeOverrideItem
        from api.services.grades_snapshot_service import GradesSnapshotServiceError

        body = GradeOverridesBody(overrides=[
            GradeOverrideItem(component_key="midterm", manual_score=80.0, manual_possible=100.0)
        ])
        fake_data = {"course_id": 1001, "grade": {"weighted_grade": 80.0}, "components": []}
        with patch("api.routers.courses._resolve_token", return_value="tok"), \
             patch("api.routers.courses.save_course_grade_overrides", return_value=fake_data), \
             patch("api.routers.courses.save_course_detail_snapshot", side_effect=GradesSnapshotServiceError("persist fail")):
            result = write_course_grade_overrides(course_id=1001, body=body, quercus_token="tok", current_user=_user())
        assert result["course_id"] == 1001


class TestRemoveCourseGradeOverrideAdditional:
    def test_delete_snapshot_persist_failure_is_swallowed(self):
        from api.routers.courses import remove_course_grade_override
        from api.services.grades_snapshot_service import GradesSnapshotServiceError

        fake_data = {"course_id": 1001, "grade": {"weighted_grade": 85.0}, "components": []}
        with patch("api.routers.courses._resolve_token", return_value="tok"), \
             patch("api.routers.courses.delete_course_grade_override", return_value=fake_data), \
             patch("api.routers.courses.save_course_detail_snapshot", side_effect=GradesSnapshotServiceError("persist fail")):
            result = remove_course_grade_override(
                course_id=1001, component_key="midterm", quercus_token="tok", current_user=_user()
            )
        assert result["course_id"] == 1001


class TestCourseWeightsErrors:
    def test_raises_400_on_weight_error(self):
        from api.routers.courses import course_weights
        from api.services.course_service import CourseServiceError
        with patch("api.routers.courses._resolve_token", return_value="tok"), \
             patch("api.routers.courses.get_course_weights", side_effect=CourseServiceError("no weights")):
            with pytest.raises(HTTPException) as exc:
                course_weights(course_id=1001, quercus_token="tok", current_user=_user())
        assert exc.value.status_code == 400
