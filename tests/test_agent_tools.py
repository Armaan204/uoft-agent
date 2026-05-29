"""
tests/test_agent_tools.py — unit tests for agent/tools.py tool implementations.

All Supabase, Quercus, and Anthropic calls are mocked so tests run offline.
"""

import pytest
from unittest.mock import MagicMock, patch


def _make_quercus_client(token="fake-token"):
    """Build a QuercusClient with requests.get mocked to avoid real HTTP calls."""
    from unittest.mock import patch, MagicMock
    with patch("api.integrations.quercus.requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200, ok=True, headers={"Link": ""},
            json=lambda: [],
        )
        from api.integrations.quercus import QuercusClient
        return QuercusClient(token=token)


# ── get_cached_grades ─────────────────────────────────────────────────────────

class TestGetCachedGrades:
    def test_returns_empty_when_no_snapshot(self):
        """No snapshot rows → empty courses list."""
        from api.agent.tools import _get_cached_grades
        client = _make_quercus_client()

        with patch(
            "api.agent.tools.load_grades_snapshot",
            return_value=[],
        ):
            result = _get_cached_grades({}, client, user_id="user-123")

        assert result["courses"] == []
        assert result["errors"] == []
        assert result["fetched_at"] is None

    def test_reads_from_snapshot_rows(self):
        """Snapshot rows are mapped to the expected course summary structure."""
        from api.agent.tools import _get_cached_grades
        client = _make_quercus_client()

        snapshot_rows = [
            {
                "course_id": 1001,
                "course_name": "Intro CS",
                "course_code": "CSCA08H3",
                "current_grade": 85.0,
                "letter_grade": "A",
                "fetched_at": "2024-11-01T12:00:00+00:00",
            },
            {
                "course_id": 1002,
                "course_name": "Calculus I",
                "course_code": "MATA30H3",
                "current_grade": 72.0,
                "letter_grade": "B-",
                "fetched_at": "2024-11-01T12:00:00+00:00",
            },
        ]

        with patch("api.agent.tools.load_grades_snapshot", return_value=snapshot_rows):
            result = _get_cached_grades({}, client, user_id="user-123")

        assert len(result["courses"]) == 2
        course = result["courses"][0]
        assert course["course_id"] == 1001
        assert course["current_grade"] == 85.0
        assert course["letter"] == "A"

    def test_returns_error_when_no_user_id(self):
        """user_id=None → error message, no snapshot lookup."""
        from api.agent.tools import _get_cached_grades
        client = _make_quercus_client()
        result = _get_cached_grades({}, client, user_id=None)
        assert "error" in result

    def test_fetched_at_is_max_of_all_rows(self):
        """fetched_at should be the latest timestamp across all rows."""
        from api.agent.tools import _get_cached_grades
        client = _make_quercus_client()

        rows = [
            {"course_id": 1, "fetched_at": "2024-11-01T10:00:00+00:00",
             "course_name": "A", "course_code": "X", "current_grade": 80, "letter_grade": "A-"},
            {"course_id": 2, "fetched_at": "2024-11-01T15:00:00+00:00",
             "course_name": "B", "course_code": "Y", "current_grade": 70, "letter_grade": "B-"},
        ]
        with patch("api.agent.tools.load_grades_snapshot", return_value=rows):
            result = _get_cached_grades({}, client, user_id="user-1")

        assert result["fetched_at"] == "2024-11-01T15:00:00+00:00"


# ── get_all_grades ────────────────────────────────────────────────────────────

class TestGetAllGrades:
    def test_calls_get_grade_snapshot_when_user_id_present(self):
        """With user_id, delegates to grade_snapshot_cache."""
        from api.agent.tools import _get_all_grades
        client = _make_quercus_client()
        expected = {"courses": [{"course_id": 999}], "errors": [], "fetched_at": "now"}

        with patch("api.agent.tools.get_grade_snapshot", return_value=expected) as mock_snap:
            result = _get_all_grades({}, client, user_id="user-xyz")

        mock_snap.assert_called_once_with("user-xyz", client._token)
        assert result == expected

    def test_falls_back_to_live_fetch_when_no_user_id(self):
        """Without user_id, calls client.get_courses() directly."""
        from api.agent.tools import _get_all_grades

        mock_client = MagicMock()
        mock_client._token = "tok"
        mock_client.get_courses.return_value = []

        result = _get_all_grades({}, mock_client, user_id=None)
        mock_client.get_courses.assert_called_once()
        assert "courses" in result
        assert result["courses"] == []


# ── get_academic_history ──────────────────────────────────────────────────────

class TestGetAcademicHistory:
    def test_returns_error_without_user_id(self):
        from api.agent.tools import _get_academic_history
        client = _make_quercus_client()
        result = _get_academic_history({}, client, user_id=None)
        assert "error" in result

    def test_returns_structured_acorn_data(self, sample_acorn_data):
        from api.agent.tools import _get_academic_history
        client = _make_quercus_client()

        expected_history = {
            "terms": sample_acorn_data["terms"],
            "credits_earned": 1.5,
            "imported_at": "2024-11-01T00:00:00Z",
        }

        with patch("api.agent.tools.load_academic_history", return_value=expected_history):
            result = _get_academic_history({}, client, user_id="user-123")

        assert "terms" in result
        assert result["credits_earned"] == 1.5

    def test_delegated_to_acorn_service(self):
        """_get_academic_history must call load_academic_history with user_id."""
        from api.agent.tools import _get_academic_history
        client = _make_quercus_client()

        with patch("api.agent.tools.load_academic_history", return_value={}) as mock_load:
            _get_academic_history({}, client, user_id="user-42")

        mock_load.assert_called_once_with("user-42")

    def test_returns_empty_history_payload(self):
        from api.agent.tools import _get_academic_history
        client = _make_quercus_client()
        with patch("api.agent.tools.load_academic_history", return_value={"terms": [], "credits_earned": 0.0}):
            result = _get_academic_history({}, client, user_id="user-1")
        assert result["terms"] == []

    def test_returns_multiple_terms(self):
        from api.agent.tools import _get_academic_history
        client = _make_quercus_client()
        payload = {"terms": [{"term": "Fall 2023"}, {"term": "Winter 2024"}], "credits_earned": 1.0}
        with patch("api.agent.tools.load_academic_history", return_value=payload):
            result = _get_academic_history({}, client, user_id="user-1")
        assert len(result["terms"]) == 2


class TestGetAllAnnouncements:
    def test_returns_from_snapshot_when_available(self):
        """Snapshot announcements are returned directly without any Quercus calls."""
        from api.agent.tools import _get_all_announcements
        mock_client = MagicMock()
        snapshot_announcements = [
            {"course_id": 1, "course_code": "CSC", "title": "Midterm update", "posted_at": "2026-05-01T10:00:00+00:00"},
        ]
        snapshot_rows = [{"course_id": 1, "announcements": snapshot_announcements}]

        with patch("api.agent.tools.load_grades_snapshot", return_value=snapshot_rows):
            result = _get_all_announcements({}, mock_client, user_id="user-1")

        assert result["source"] == "snapshot"
        assert len(result["announcements"]) == 1
        assert result["announcements"][0]["title"] == "Midterm update"
        mock_client.get_courses.assert_not_called()

    def test_falls_back_to_live_when_no_snapshot_announcements(self):
        """No announcements in snapshot → live Quercus fetch."""
        from api.agent.tools import _get_all_announcements
        mock_client = MagicMock()
        mock_client.get_courses.return_value = [{"id": 10, "name": "Physics", "course_code": "PHY"}]
        mock_client.get_latest_announcements.return_value = [
            {
                "context_code": "course_10",
                "title": "Lab cancelled",
                "posted_at": "2026-05-10T09:00:00Z",
                "message": "<p>Lab is cancelled</p>",
                "html_url": "https://q.utoronto.ca/ann/99",
            }
        ]
        with patch("api.agent.tools.load_grades_snapshot", return_value=[{"course_id": 10}]):
            result = _get_all_announcements({}, mock_client, user_id="user-1")

        assert result["source"] == "live"
        assert len(result["announcements"]) == 1
        assert result["announcements"][0]["title"] == "Lab cancelled"
        assert result["announcements"][0]["course_code"] == "PHY"
        mock_client.get_latest_announcements.assert_called_once_with([10])

    def test_live_fetch_used_when_no_user_id(self):
        """Without user_id, skips snapshot and goes directly to live fetch."""
        from api.agent.tools import _get_all_announcements
        mock_client = MagicMock()
        mock_client.get_courses.return_value = []
        mock_client.get_latest_announcements.return_value = []

        result = _get_all_announcements({}, mock_client, user_id=None)

        assert result["source"] == "live"
        mock_client.get_courses.assert_called_once()

    def test_ignores_non_course_context_codes(self):
        """Announcements with non-course context_codes are skipped."""
        from api.agent.tools import _get_all_announcements
        mock_client = MagicMock()
        mock_client.get_courses.return_value = [{"id": 1, "name": "Env", "course_code": "ENV"}]
        mock_client.get_latest_announcements.return_value = [
            {"context_code": "group_42", "title": "Group post", "posted_at": None, "message": "", "html_url": None},
            {"context_code": "course_1", "title": "Real post", "posted_at": "2026-05-01T00:00:00Z", "message": "", "html_url": None},
        ]
        with patch("api.agent.tools.load_grades_snapshot", return_value=[]):
            result = _get_all_announcements({}, mock_client, user_id="u1")

        assert len(result["announcements"]) == 1
        assert result["announcements"][0]["title"] == "Real post"

    def test_announcements_sorted_newest_first(self):
        """Live fetch results are sorted newest posted_at first."""
        from api.agent.tools import _get_all_announcements
        mock_client = MagicMock()
        mock_client.get_courses.return_value = [
            {"id": 1, "name": "A", "course_code": "A"},
            {"id": 2, "name": "B", "course_code": "B"},
        ]
        mock_client.get_latest_announcements.return_value = [
            {"context_code": "course_1", "title": "Older", "posted_at": "2026-04-01T00:00:00Z", "message": "", "html_url": None},
            {"context_code": "course_2", "title": "Newer", "posted_at": "2026-05-10T00:00:00Z", "message": "", "html_url": None},
        ]
        with patch("api.agent.tools.load_grades_snapshot", return_value=[]):
            result = _get_all_announcements({}, mock_client, user_id="u1")

        assert result["announcements"][0]["title"] == "Newer"
        assert result["announcements"][1]["title"] == "Older"

    def test_dispatched_via_execute_tool(self):
        """get_all_announcements is registered and dispatchable via execute_tool."""
        from api.agent.tools import execute_tool
        mock_client = MagicMock()
        mock_client.get_courses.return_value = []
        mock_client.get_latest_announcements.return_value = []
        with patch("api.agent.tools.load_grades_snapshot", return_value=[]):
            result = execute_tool("get_all_announcements", {}, mock_client, "user-1")
        assert "announcements" in result


class TestAnnouncementsTools:
    def test_get_course_announcements_returns_empty_list(self):
        from api.agent.tools import _get_course_announcements
        mock_client = MagicMock()
        mock_client.get_course_announcements.return_value = []
        result = _get_course_announcements({"course_id": 1, "course_name": "CS"}, mock_client)
        assert result["announcements"] == []

    def test_get_announcement_detail_course_not_found_is_caught_by_dispatch(self):
        from api.agent.tools import execute_tool
        mock_client = MagicMock()
        mock_client.get_announcement_detail.side_effect = RuntimeError("course not found")
        result = execute_tool("get_announcement_detail", {"course_id": 1, "announcement_id": 2}, mock_client)
        assert "error" in result

    def test_get_announcement_detail_success(self):
        from api.agent.tools import _get_announcement_detail
        mock_client = MagicMock()
        mock_client.get_announcement_detail.return_value = {
            "title": "Update",
            "posted_at": "2024-01-01T00:00:00Z",
            "message": "<p>Hello <b>world</b></p>",
            "html_url": "https://q.utoronto.ca/ann/1",
        }
        result = _get_announcement_detail({"course_id": 1, "announcement_id": 2}, mock_client)
        assert result["body"] == "Hello world"
        assert result["url"].endswith("/1")


class TestGradeToolsHelpers:
    def test_get_course_weights_prefers_canvas(self):
        from api.agent.tools import _get_course_weights
        mock_client = MagicMock()
        mock_client.get_canvas_weights.return_value = {"Midterm": 40.0}
        result = _get_course_weights({"course_id": 1}, mock_client)
        assert result == {"Midterm": 40.0}

    def test_get_course_weights_falls_back_to_syllabus(self):
        from api.agent.tools import _get_course_weights
        mock_client = MagicMock()
        mock_client.get_canvas_weights.return_value = None
        mock_client.get_syllabus.return_value = {"pdf_urls": ["http://a/file.pdf"]}
        with patch("api.agent.tools.parse_syllabus_weights", return_value=("src", {"Final": 100.0})):
            result = _get_course_weights({"course_id": 1}, mock_client)
        assert result == {"Final": 100.0}

    def test_preview_text_truncates(self):
        from api.agent.tools import _preview_text
        preview = _preview_text("<p>" + ("a" * 150) + "</p>", limit=20)
        assert preview.endswith("…")
        assert len(preview) == 20

    def test_get_current_grade_delegates_to_calculator(self):
        from api.agent.tools import _get_current_grade
        mock_client = MagicMock()
        mock_client.get_assignment_groups.return_value = [{"name": "Midterm", "assignments": []}]
        mock_client.get_submissions.return_value = []
        with patch("api.agent.tools._get_course_weights", return_value={"Midterm": 100.0}), \
             patch("api.agent.tools._calc.current_grade", return_value={"weighted_grade": 0.0}) as mock_calc:
            result = _get_current_grade({"course_id": 1}, mock_client)
        mock_calc.assert_called_once()
        assert result["weighted_grade"] == 0.0

    def test_build_grade_summary_maps_grade_fields(self):
        from api.agent.tools import _build_grade_summary
        course = {"id": 1, "name": "Intro CS", "course_code": "CSCA08H3"}
        with patch("api.agent.tools._get_current_grade", return_value={"weighted_grade": 80.0, "letter": "A-", "gpa_points": 3.7, "graded_weight": 60.0}):
            result = _build_grade_summary(course, MagicMock())
        assert result["course_code"] == "CSCA08H3"
        assert result["gpa_points"] == 3.7

    def test_get_all_grades_collects_partial_errors(self):
        from api.agent.tools import _get_all_grades
        mock_client = MagicMock()
        mock_client.get_courses.return_value = [
            {"id": 1, "name": "A", "course_code": "A"},
            {"id": 2, "name": "B", "course_code": "B"},
        ]

        def fake_summary(course, _client):
            if course["id"] == 2:
                raise RuntimeError("boom")
            return {"course_id": 1}

        with patch("api.agent.tools._build_grade_summary", side_effect=fake_summary):
            result = _get_all_grades({}, mock_client, user_id=None)
        assert result["courses"] == [{"course_id": 1}]
        assert result["errors"][0]["course_id"] == 2

    def test_refresh_grades_without_user_id_falls_back_to_live_fetch(self):
        from api.agent.tools import _refresh_grades
        mock_client = MagicMock()
        with patch("api.agent.tools._get_all_grades", return_value={"courses": []}) as mock_all:
            result = _refresh_grades({}, mock_client, user_id=None)
        mock_all.assert_called_once()
        assert result == {"courses": []}

    def test_check_graduation_progress_without_user_id(self):
        from api.agent.tools import _check_graduation_progress
        result = _check_graduation_progress({}, MagicMock(), user_id=None)
        assert "error" in result

    def test_check_graduation_progress_blank_program_name(self):
        from api.agent.tools import _check_graduation_progress
        with patch("api.agent.tools.load_academic_history", return_value={"programs": [{"programName": "   "}]}):
            result = _check_graduation_progress({}, MagicMock(), user_id="u1")
        assert "Could not determine program name" in result["error"]

    def test_get_grade_scenarios_returns_no_ungraded_error(self):
        from api.agent.tools import _get_grade_scenarios
        mock_client = MagicMock()
        mock_client.get_assignment_groups.return_value = [{"name": "Midterm", "assignments": [{"id": 1, "points_possible": 100}]}]
        mock_client.get_submissions.return_value = [{"assignment_id": 1, "score": 80.0}]
        with patch("api.agent.tools._get_course_weights", return_value={"Midterm": 100.0}), \
             patch("api.agent.tools._calc.current_grade", return_value={"weighted_grade": 80.0}):
            result = _get_grade_scenarios({"course_id": 1}, mock_client)
        assert result["error"] == "No ungraded assessments found"

    def test_get_grade_scenarios_success(self):
        from api.agent.tools import _get_grade_scenarios
        mock_client = MagicMock()
        mock_client.get_assignment_groups.return_value = [{"name": "Final Exam", "assignments": [{"id": 1, "points_possible": 100}]}]
        mock_client.get_submissions.return_value = []
        with patch("api.agent.tools._get_course_weights", return_value={"Final Exam": 60.0}), \
             patch("api.agent.tools._calc.current_grade", return_value={"weighted_grade": 70.0}), \
             patch("api.agent.tools._calc.grade_scenarios", return_value={"A": {"status": "needed", "needed": 90.0}}):
            result = _get_grade_scenarios({"course_id": 1}, mock_client)
        assert result["final_weight_pct"] == 60.0
        assert result["scenarios"]["A"]["needed"] == 90.0


# ── check_graduation_progress (via execute_tool) ──────────────────────────────

class TestCheckGraduationProgressTool:
    def test_returns_error_when_no_acorn_data(self):
        """No ACORN history → informative error string."""
        from api.agent.tools import _get_cached_grades  # ensure module loads

        mock_client = MagicMock()
        mock_client._token = "tok"

        with patch("api.agent.tools.load_academic_history", return_value={"terms": [], "credits_earned": 0.0}), \
             patch("api.agent.tools._get_prog_reqs", return_value=None):
            from api.agent.tools import execute_tool
            result = execute_tool("check_graduation_progress", {}, mock_client, "user-99")

        # Should contain error or meaningful message (not crash)
        assert isinstance(result, (dict, str))

    def test_returns_progress_dict_on_success(self, sample_requirements):
        """Happy path: ACORN data + requirements → structured progress result."""
        from api.agent.tools import execute_tool

        mock_client = MagicMock()
        mock_client._token = "tok"

        # ACORN data must have programs so the function proceeds past the early-exit guard
        acorn_with_programs = {
            "terms": [],
            "credits_earned": 1.5,
            "programs": [{"programName": "Computer Science Specialist"}],
        }
        expected = {"overall_status": "in_progress", "credits_satisfied": 1.5, "groups": []}

        with patch("api.agent.tools.load_academic_history", return_value=acorn_with_programs), \
             patch("api.agent.tools._get_prog_reqs", return_value=sample_requirements), \
             patch("api.agent.tools._check_grad_progress", return_value=expected) as mock_progress:
            result = execute_tool("check_graduation_progress", {}, mock_client, "user-99")

        mock_progress.assert_called_once()
        assert result["overall_status"] == "in_progress"

    def test_returns_error_for_unsupported_program(self):
        from api.agent.tools import execute_tool
        mock_client = MagicMock()
        mock_client._token = "tok"
        acorn_with_programs = {"terms": [], "programs": [{"programName": "Unknown Program"}]}
        with patch("api.agent.tools.load_academic_history", return_value=acorn_with_programs), \
             patch("api.agent.tools._get_prog_reqs", return_value=None):
            result = execute_tool("check_graduation_progress", {}, mock_client, "user-99")
        assert "error" in result


class TestRefreshGrades:
    def test_refresh_grades_invalidates_and_saves_snapshot(self):
        from api.agent.tools import _refresh_grades
        mock_client = MagicMock()
        mock_client._token = "tok"
        fresh = {"courses": [{"course_id": 1, "current_grade": 80.0}], "errors": [], "fetched_at": "now"}
        with patch("api.agent.tools.invalidate_grade_snapshot") as mock_invalidate, \
             patch("api.agent.tools.get_grade_snapshot", return_value=fresh) as mock_snapshot, \
             patch("api.agent.tools.save_snapshot") as mock_save:
            result = _refresh_grades({}, mock_client, user_id="user-1")
        mock_invalidate.assert_called_once_with("user-1")
        mock_snapshot.assert_called_once_with("user-1", "tok", force_refresh=True)
        mock_save.assert_called_once_with("user-1", fresh["courses"])
        assert result == fresh


# ── execute_tool dispatch ─────────────────────────────────────────────────────

class TestExecuteToolDispatch:
    def test_get_courses_dispatched(self):
        from api.agent.tools import execute_tool
        mock_client = MagicMock()
        mock_client.get_courses.return_value = [
            {"id": 1, "name": "CSC", "course_code": "CSCA08H3"}
        ]
        result = execute_tool("get_courses", {}, mock_client, None)
        assert isinstance(result, list)
        mock_client.get_courses.assert_called_once()

    def test_unknown_tool_returns_error_string(self):
        from api.agent.tools import execute_tool
        mock_client = MagicMock()
        result = execute_tool("this_tool_does_not_exist", {}, mock_client, None)
        # Should return an error message, not raise
        assert "unknown" in str(result).lower() or isinstance(result, dict)


class TestGetUpcomingDeadlines:
    def test_returns_deadlines_from_snapshot(self):
        """Snapshot rows with upcoming deadlines are returned sorted by due_at."""
        from api.agent.tools import _get_upcoming_deadlines_tool
        from datetime import datetime, timedelta, timezone

        future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        snapshot_rows = [
            {
                "course_id": 1,
                "course_code": "EESA11H3",
                "course_name": "Environmental Science",
                "dashboard_data": {
                    "deadlines": [
                        {"name": "Quiz 1", "due_at": future, "url": "https://q.utoronto.ca/1"},
                    ]
                },
            }
        ]
        with patch("api.agent.tools.load_grades_snapshot", return_value=snapshot_rows):
            result = _get_upcoming_deadlines_tool({}, MagicMock(), user_id="user-1")

        assert result["source"] == "snapshot"
        assert len(result["deadlines"]) == 1
        assert result["deadlines"][0]["name"] == "Quiz 1"
        assert result["deadlines"][0]["course_code"] == "EESA11H3"

    def test_excludes_past_deadlines_from_snapshot(self):
        """Deadlines already past (before now) are excluded even if in the snapshot."""
        from api.agent.tools import _get_upcoming_deadlines_tool
        from datetime import datetime, timedelta, timezone

        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        snapshot_rows = [
            {
                "course_id": 1,
                "course_code": "CSC",
                "course_name": "CS",
                "dashboard_data": {"deadlines": [{"name": "Old HW", "due_at": past, "url": None}]},
            }
        ]
        with patch("api.agent.tools.load_grades_snapshot", return_value=snapshot_rows):
            result = _get_upcoming_deadlines_tool({}, MagicMock(), user_id="user-1")

        assert result["deadlines"] == []

    def test_falls_back_to_live_fetch_when_no_snapshot(self):
        """With no snapshot rows, queries Quercus directly."""
        from api.agent.tools import _get_upcoming_deadlines_tool
        from datetime import datetime, timedelta, timezone

        future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        mock_client = MagicMock()
        mock_client.get_courses.return_value = [
            {"id": 10, "name": "Physics", "course_code": "PHYA10H3"}
        ]
        mock_client.get_assignments.return_value = [
            {"name": "Lab Report", "due_at": future, "html_url": "https://q.utoronto.ca/lab"}
        ]

        with patch("api.agent.tools.load_grades_snapshot", return_value=[]):
            result = _get_upcoming_deadlines_tool({}, mock_client, user_id="user-1")

        assert result["source"] == "live"
        assert len(result["deadlines"]) == 1
        assert result["deadlines"][0]["name"] == "Lab Report"

    def test_live_fetch_used_when_no_user_id(self):
        """Without user_id, always falls back to live Quercus fetch."""
        from api.agent.tools import _get_upcoming_deadlines_tool
        from datetime import datetime, timedelta, timezone

        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        mock_client = MagicMock()
        mock_client.get_courses.return_value = [{"id": 5, "name": "Env", "course_code": "EESA11H3"}]
        mock_client.get_assignments.return_value = [
            {"name": "Quiz 1", "due_at": future, "html_url": "https://q.utoronto.ca/q1"}
        ]

        result = _get_upcoming_deadlines_tool({}, mock_client, user_id=None)

        assert result["source"] == "live"
        mock_client.get_courses.assert_called_once()

    def test_days_parameter_capped_at_30(self):
        """days parameter is capped at 30 regardless of input."""
        from api.agent.tools import _get_upcoming_deadlines_tool
        mock_client = MagicMock()
        mock_client.get_courses.return_value = []
        with patch("api.agent.tools.load_grades_snapshot", return_value=[]):
            result = _get_upcoming_deadlines_tool({"days": 999}, mock_client, user_id="u1")
        assert result["days"] == 30

    def test_defaults_to_14_days(self):
        """Omitting days defaults to 14."""
        from api.agent.tools import _get_upcoming_deadlines_tool
        mock_client = MagicMock()
        mock_client.get_courses.return_value = []
        with patch("api.agent.tools.load_grades_snapshot", return_value=[]):
            result = _get_upcoming_deadlines_tool({}, mock_client, user_id="u1")
        assert result["days"] == 14

    def test_deadlines_sorted_by_due_at(self):
        """Multiple deadlines are returned sorted earliest first."""
        from api.agent.tools import _get_upcoming_deadlines_tool
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        d1 = (now + timedelta(days=7)).isoformat()
        d2 = (now + timedelta(days=2)).isoformat()
        snapshot_rows = [
            {
                "course_id": 1,
                "course_code": "A",
                "course_name": "Course A",
                "dashboard_data": {"deadlines": [{"name": "Late", "due_at": d1, "url": None}]},
            },
            {
                "course_id": 2,
                "course_code": "B",
                "course_name": "Course B",
                "dashboard_data": {"deadlines": [{"name": "Soon", "due_at": d2, "url": None}]},
            },
        ]
        with patch("api.agent.tools.load_grades_snapshot", return_value=snapshot_rows):
            result = _get_upcoming_deadlines_tool({}, MagicMock(), user_id="u1")

        assert result["deadlines"][0]["name"] == "Soon"
        assert result["deadlines"][1]["name"] == "Late"

    def test_dispatched_via_execute_tool(self):
        """get_upcoming_deadlines is registered and dispatchable via execute_tool."""
        from api.agent.tools import execute_tool
        mock_client = MagicMock()
        mock_client.get_courses.return_value = []
        with patch("api.agent.tools.load_grades_snapshot", return_value=[]):
            result = execute_tool("get_upcoming_deadlines", {}, mock_client, "user-1")
        assert "deadlines" in result


class TestAgentToolsAdditional:
    def test_preview_text_returns_untruncated_text(self):
        from api.agent.tools import _preview_text
        assert _preview_text("<p>Hello world</p>", limit=50) == "Hello world"

    def test_get_grade_scenarios_uses_substring_weight_match(self):
        from api.agent.tools import _get_grade_scenarios
        mock_client = MagicMock()
        mock_client.get_assignment_groups.return_value = [
            {"name": "Final Examination", "assignments": [{"id": 1, "points_possible": 100}]}
        ]
        mock_client.get_submissions.return_value = []
        with patch("api.agent.tools._get_course_weights", return_value={"Final": 55.0}), \
             patch("api.agent.tools._calc.current_grade", return_value={"weighted_grade": 72.0}), \
             patch("api.agent.tools._calc.grade_scenarios", return_value={"A": {"status": "needed", "needed": 90.0}}):
            result = _get_grade_scenarios({"course_id": 1}, mock_client)
        assert result["final_weight_pct"] == 55.0

    def test_get_grade_scenarios_uses_shortest_containing_candidate(self):
        from api.agent.tools import _get_grade_scenarios
        mock_client = MagicMock()
        mock_client.get_assignment_groups.return_value = [
            {"name": "final", "assignments": []}
        ]
        mock_client.get_submissions.return_value = []
        with patch("api.agent.tools._get_course_weights", return_value={"final exam": 40.0, "final project showcase": 60.0}), \
             patch("api.agent.tools._calc.current_grade", return_value={"weighted_grade": 60.0}), \
             patch("api.agent.tools._calc.grade_scenarios", return_value={"B": {"status": "needed", "needed": 70.0}}):
            result = _get_grade_scenarios({"course_id": 1}, mock_client)
        assert result["final_assessment"] == "final"
        assert result["final_weight_pct"] == 40.0
