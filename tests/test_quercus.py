"""
tests/test_quercus.py — unit tests for integrations/quercus.py.

All HTTP calls are mocked via unittest.mock.patch so tests run offline.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call

from api.integrations.quercus import QuercusClient, QuercusAuthError, QuercusError


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_response(data, status_code=200, link_header=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = status_code < 400
    resp.json.return_value = data
    resp.headers = {"Link": link_header}
    resp.text = ""
    return resp


def _current_term_dates():
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end   = (now + timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return start, end


def _past_term_dates():
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end   = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return start, end


def _future_term_dates(days_ahead=10):
    now = datetime.now(timezone.utc)
    start = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end   = (now + timedelta(days=days_ahead + 90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return start, end


# ── get_courses ───────────────────────────────────────────────────────────────

class TestGetCourses:
    def test_returns_current_term_courses_only(self):
        """Only courses whose term spans today are returned."""
        cur_start, cur_end = _current_term_dates()
        past_start, past_end = _past_term_dates()

        courses_data = [
            {
                "id": 1001,
                "name": "Intro to CS",
                "course_code": "CSCA08H3",
                "enrollment_state": "active",
                "term": {"id": 10, "name": "Fall 2024", "start_at": cur_start, "end_at": cur_end},
            },
            {
                "id": 2001,
                "name": "Old Course",
                "course_code": "OLD001",
                "enrollment_state": "active",
                "term": {"id": 9, "name": "Fall 2023", "start_at": past_start, "end_at": past_end},
            },
        ]

        with patch("api.integrations.quercus.requests.get", return_value=_mock_response(courses_data)):
            client = QuercusClient(token="fake-token")
            courses = client.get_courses()

        ids = [c["id"] for c in courses]
        assert 1001 in ids, "Current term course should be included"
        assert 2001 not in ids, "Past term course should be excluded"

    def test_falls_back_to_nearest_upcoming_when_no_current(self):
        """When no course is active today, returns the nearest upcoming term."""
        near_start, near_end = _future_term_dates(days_ahead=5)
        far_start, far_end   = _future_term_dates(days_ahead=50)

        courses_data = [
            {
                "id": 3001,
                "name": "Near Future Course",
                "course_code": "NEAR01",
                "enrollment_state": "active",
                "term": {"id": 11, "name": "Summer 2025", "start_at": near_start, "end_at": near_end},
            },
            {
                "id": 4001,
                "name": "Far Future Course",
                "course_code": "FAR001",
                "enrollment_state": "active",
                "term": {"id": 12, "name": "Fall 2025", "start_at": far_start, "end_at": far_end},
            },
        ]

        with patch("api.integrations.quercus.requests.get", return_value=_mock_response(courses_data)):
            client = QuercusClient(token="fake-token")
            courses = client.get_courses()

        ids = [c["id"] for c in courses]
        assert 3001 in ids, "Near upcoming course should be included"
        # Far-future course (50 days away) is outside the 45-day window
        assert 4001 not in ids

    def test_excludes_resource_page_courses(self):
        """Courses matching resource-page keywords are filtered out."""
        cur_start, cur_end = _current_term_dates()

        courses_data = [
            {
                "id": 9999,
                "name": "CS Undergrads Community Hub",
                "course_code": "RESOURCE",
                "enrollment_state": "active",
                "term": {"id": 10, "name": "Fall 2024", "start_at": cur_start, "end_at": cur_end},
            },
            {
                "id": 1001,
                "name": "CSCA08 Programming",
                "course_code": "CSCA08H3",
                "enrollment_state": "active",
                "term": {"id": 10, "name": "Fall 2024", "start_at": cur_start, "end_at": cur_end},
            },
        ]

        with patch("api.integrations.quercus.requests.get", return_value=_mock_response(courses_data)):
            client = QuercusClient(token="fake-token")
            courses = client.get_courses()

        assert all(c["id"] != 9999 for c in courses), "Resource page should be filtered"
        assert any(c["id"] == 1001 for c in courses)

    def test_excludes_courses_without_term_dates(self):
        """Courses with no term start/end are excluded."""
        cur_start, cur_end = _current_term_dates()

        courses_data = [
            {
                "id": 8888,
                "name": "No Term Course",
                "course_code": "NT001",
                "enrollment_state": "active",
                "term": {"id": 0, "name": "Default Term", "start_at": None, "end_at": None},
            },
            {
                "id": 1001,
                "name": "Real Course",
                "course_code": "CSCA08H3",
                "enrollment_state": "active",
                "term": {"id": 10, "name": "Fall 2024", "start_at": cur_start, "end_at": cur_end},
            },
        ]

        with patch("api.integrations.quercus.requests.get", return_value=_mock_response(courses_data)):
            client = QuercusClient(token="fake-token")
            courses = client.get_courses()

        assert all(c["id"] != 8888 for c in courses)

    def test_raises_auth_error_on_401(self):
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response({}, 401)):
            client = QuercusClient(token="bad-token")
            with pytest.raises(QuercusAuthError):
                client.get_courses()

    def test_raises_quercus_error_on_5xx(self):
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response({}, 500)):
            client = QuercusClient(token="tok")
            with pytest.raises(QuercusError):
                client.get_courses()

    def test_handles_pagination_across_multiple_pages(self):
        cur_start, cur_end = _current_term_dates()
        resp1 = _mock_response(
            [{"id": 1, "name": "Course 1", "course_code": "CSCA08H3", "term": {"start_at": cur_start, "end_at": cur_end}}],
            link_header='<https://q.utoronto.ca/api/v1/courses?page=2>; rel="next"',
        )
        resp2 = _mock_response(
            [{"id": 2, "name": "Course 2", "course_code": "MATA30H3", "term": {"start_at": cur_start, "end_at": cur_end}}]
        )
        with patch("api.integrations.quercus.requests.get", side_effect=[resp1, resp2]):
            client = QuercusClient(token="tok")
            courses = client.get_courses()
        assert {course["id"] for course in courses} == {1, 2}

    def test_returns_empty_when_no_courses_are_eligible(self):
        courses_data = [
            {"id": 1, "name": "Sandbox", "course_code": "TEST", "term": {"start_at": None, "end_at": None}},
            {"id": 2, "name": "CS Undergrads Community", "course_code": "COMM", "term": {"start_at": None, "end_at": None}},
        ]
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response(courses_data)):
            client = QuercusClient(token="tok")
            assert client.get_courses() == []


# ── get_assignment_groups ─────────────────────────────────────────────────────

class TestGetAssignmentGroups:
    def test_returns_groups_with_nested_assignments(self):
        groups_data = [
            {
                "id": 10, "name": "Midterm", "group_weight": 40.0,
                "rules": {},
                "assignments": [
                    {"id": 101, "name": "Midterm Exam", "points_possible": 100}
                ],
            },
        ]
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response(groups_data)):
            client = QuercusClient(token="tok")
            groups = client.get_assignment_groups(9001)

        assert len(groups) == 1
        assert groups[0]["name"] == "Midterm"
        assert groups[0]["assignments"][0]["id"] == 101

    def test_handles_pagination(self):
        """If the first page has a 'next' link, the second page is fetched."""
        page1 = [{"id": 10, "name": "Group A", "group_weight": 50.0, "rules": {}, "assignments": []}]
        page2 = [{"id": 20, "name": "Group B", "group_weight": 50.0, "rules": {}, "assignments": []}]

        resp1 = _mock_response(page1, link_header='<https://q.utoronto.ca/api/v1/page2>; rel="next"')
        resp2 = _mock_response(page2)

        with patch("api.integrations.quercus.requests.get", side_effect=[resp1, resp2]):
            client = QuercusClient(token="tok")
            groups = client.get_assignment_groups(9001)

        assert len(groups) == 2
        names = {g["name"] for g in groups}
        assert "Group A" in names
        assert "Group B" in names

    def test_preserves_never_drop_rules(self):
        groups_data = [
            {
                "id": 10,
                "name": "Quizzes",
                "group_weight": 100.0,
                "rules": {"never_drop": [123]},
                "assignments": [],
            }
        ]
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response(groups_data)):
            client = QuercusClient(token="tok")
            groups = client.get_assignment_groups(9001)
        assert groups[0]["rules"]["never_drop"] == [123]


# ── get_canvas_weights ────────────────────────────────────────────────────────

class TestGetCanvasWeights:
    def test_returns_weights_when_configured(self):
        """Returns a dict of name→weight when groups have non-zero weights summing to ~100%."""
        groups_data = [
            {"id": 1, "name": "Midterm",     "group_weight": 40.0, "rules": {}, "assignments": []},
            {"id": 2, "name": "Final",       "group_weight": 40.0, "rules": {}, "assignments": []},
            {"id": 3, "name": "Assignments", "group_weight": 20.0, "rules": {}, "assignments": []},
        ]
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response(groups_data)):
            client = QuercusClient(token="tok")
            weights = client.get_canvas_weights(9001)

        assert weights is not None
        assert weights["Midterm"] == pytest.approx(40.0)
        assert weights["Final"] == pytest.approx(40.0)

    def test_returns_none_when_all_weights_zero(self):
        """When all group_weight are 0, returns None (syllabus fallback needed)."""
        groups_data = [
            {"id": 1, "name": "Assignments", "group_weight": 0.0, "rules": {}, "assignments": []},
        ]
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response(groups_data)):
            client = QuercusClient(token="tok")
            assert client.get_canvas_weights(9001) is None

    def test_returns_none_when_weights_dont_sum_to_100(self):
        """Weights that sum to far from 100% (e.g. 60%) → None."""
        groups_data = [
            {"id": 1, "name": "Midterm", "group_weight": 30.0, "rules": {}, "assignments": []},
            {"id": 2, "name": "Final",   "group_weight": 30.0, "rules": {}, "assignments": []},
        ]
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response(groups_data)):
            client = QuercusClient(token="tok")
            assert client.get_canvas_weights(9001) is None


# ── get_submissions ───────────────────────────────────────────────────────────

class TestGetSubmissions:
    def test_returns_submission_list(self):
        subs_data = [
            {"assignment_id": 101, "score": 78.0, "grade": "C+"},
            {"assignment_id": 201, "score": None, "grade": None},
        ]
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response(subs_data)):
            client = QuercusClient(token="tok")
            subs = client.get_submissions(9001)

        assert len(subs) == 2
        assert subs[0]["assignment_id"] == 101
        assert subs[0]["score"] == pytest.approx(78.0)

    def test_late_submissions_are_returned_unchanged(self):
        subs_data = [{"assignment_id": 101, "score": 78.0, "late": True}]
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response(subs_data)):
            client = QuercusClient(token="tok")
            subs = client.get_submissions(9001)
        assert subs[0]["late"] is True


class TestLowLevelClientHelpers:
    def test_private_get_returns_dict_object_directly(self):
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response({"id": 1, "url": "x"})):
            client = QuercusClient(token="tok")
            assert client._get("/files/1") == {"id": 1, "url": "x"}

    def test_cached_paginated_get_returns_single_object(self):
        from api.integrations.quercus import _cached_paginated_get
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response({"id": 1})):
            result = _cached_paginated_get("tok", "/files/1")
        assert result == {"id": 1}

    def test_get_file_download_url_raises_when_missing(self):
        with patch.object(QuercusClient, "_get", return_value={}):
            client = QuercusClient(token="tok")
            with pytest.raises(QuercusError):
                client.get_file_download_url(1)

    def test_get_front_page_and_page_delegate_to_get(self):
        with patch.object(QuercusClient, "_get", side_effect=[{"body": "x"}, {"title": "y"}]) as mock_get:
            client = QuercusClient(token="tok")
            assert client.get_front_page(1)["body"] == "x"
            assert client.get_page(1, "outline")["title"] == "y"
        assert mock_get.call_count == 2

    def test_get_grades_raises_when_no_enrollment(self):
        with patch.object(QuercusClient, "_get", return_value=[]):
            client = QuercusClient(token="tok")
            with pytest.raises(QuercusError):
                client.get_grades(1)

    def test_get_course_announcements_sorts_and_limits(self):
        with patch.object(QuercusClient, "_get", return_value=[
            {"id": 1, "posted_at": "2024-01-01T00:00:00Z"},
            {"id": 2, "posted_at": "2024-02-01T00:00:00Z"},
        ]):
            client = QuercusClient(token="tok")
            result = client.get_course_announcements(1, limit=1)
        assert result[0]["id"] == 2

    def test_get_announcement_detail_delegates_to_get(self):
        with patch.object(QuercusClient, "_get", return_value={"id": 5}) as mock_get:
            client = QuercusClient(token="tok")
            result = client.get_announcement_detail(5)
        mock_get.assert_called_once()
        assert result["id"] == 5


class TestGetSyllabus:
    def test_collects_multiple_pdf_links_and_deduplicates_file_ids(self):
        course = {
            "syllabus_body": (
                '<a href="/courses/1/files/10/download">Syllabus</a>'
                '<a href="/courses/1/files/11/download">Outline</a>'
                '<a href="/courses/1/files/10/download">Duplicate</a>'
            )
        }
        with patch.object(QuercusClient, "_get", return_value=course), \
             patch.object(QuercusClient, "get_file_download_url", side_effect=["http://a/10.pdf", "http://a/11.pdf"]):
            client = QuercusClient(token="tok")
            result = client.get_syllabus(1)
        assert result["pdf_urls"] == ["http://a/10.pdf", "http://a/11.pdf"]

    def test_skips_file_urls_that_fail_to_resolve(self):
        course = {
            "syllabus_body": '<a href="/courses/1/files/10/download">Syllabus</a>'
        }
        with patch.object(QuercusClient, "_get", return_value=course), \
             patch.object(QuercusClient, "get_file_download_url", side_effect=QuercusError("boom")):
            client = QuercusClient(token="tok")
            result = client.get_syllabus(1)
        assert result["pdf_urls"] == []


class TestLowLevelErrors:
    def test_rate_limit_429_raises_quercus_error(self):
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response({}, 429)):
            client = QuercusClient(token="tok")
            with pytest.raises(QuercusError):
                client.get_assignments(1)

    def test_get_course_files_returns_empty_list_on_403(self):
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response({}, 403)):
            client = QuercusClient(token="tok")
            assert client.get_course_files(1) == []

    def test_get_course_files_reraises_non_403_error(self):
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response({}, 500)):
            client = QuercusClient(token="tok")
            with pytest.raises(QuercusError):
                client.get_course_files(1)

    def test_get_file_download_url_returns_resolved_url(self):
        with patch.object(QuercusClient, "_get", return_value={"url": "http://a/file.pdf"}):
            client = QuercusClient(token="tok")
            assert client.get_file_download_url(1) == "http://a/file.pdf"

    def test_get_courses_falls_back_to_latest_ended_term(self):
        start1, end1 = _past_term_dates()
        start2 = (datetime.now(timezone.utc) - timedelta(days=120)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end2 = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        courses_data = [
            {"id": 1, "name": "Older", "course_code": "A", "term": {"start_at": start1, "end_at": end1}},
            {"id": 2, "name": "Latest", "course_code": "B", "term": {"start_at": start2, "end_at": end2}},
        ]
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response(courses_data)):
            client = QuercusClient(token="tok")
            result = client.get_courses()
        assert [course["id"] for course in result] == [2]


# ── drop rule via get_course_grades (end-to-end calc integration) ─────────────

class TestDropRuleIntegration:
    """Verify that drop rules in Canvas groups flow through the grade calculator."""

    def test_drop_lowest_applied_to_grade(self):
        """Canvas groups with drop_lowest=1 → lower quiz dropped from grade calc."""
        from api.calculator.grades import GradeCalculator

        groups = [
            {
                "id": 50, "name": "Quizzes",
                "group_weight": 100.0,
                "rules": {"drop_lowest": 1},
                "assignments": [
                    {"id": 501, "name": "Q1", "points_possible": 10},
                    {"id": 502, "name": "Q2", "points_possible": 10},
                    {"id": 503, "name": "Q3", "points_possible": 10},
                ],
            }
        ]
        subs = [
            {"assignment_id": 501, "score": 4.0},   # 40% — should be dropped
            {"assignment_id": 502, "score": 7.0},   # 70%
            {"assignment_id": 503, "score": 10.0},  # 100%
        ]
        weights = {"Quizzes": 100.0}
        calc = GradeCalculator()
        result = calc.current_grade(groups, subs, weights)

        # Q1 dropped → (7+10)/(10+10) = 85%
        assert result["weighted_grade"] == pytest.approx(85.0, abs=0.1)
        assert 501 in result["dropped_assignment_ids"]

    def test_syllabus_fallback_used_when_canvas_weights_zero(self):
        """
        When get_canvas_weights returns None (all zero), the caller is expected
        to fall back to syllabus parsing.  This tests that the client correctly
        signals the fallback condition.
        """
        groups_data = [
            {"id": 1, "name": "Total", "group_weight": 0.0, "rules": {}, "assignments": []}
        ]
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response(groups_data)):
            client = QuercusClient(token="tok")
            weights = client.get_canvas_weights(9001)

        assert weights is None, "Should return None when canvas weights are not configured"


class TestQuercusAdditional:
    def test_init_no_token_creates_tokenless_client(self, monkeypatch):
        monkeypatch.delenv("QUERCUS_API_TOKEN", raising=False)
        c = QuercusClient(token=None)
        assert c._token is None

    def test_cached_paginated_get_raises_auth_and_http_errors(self):
        from api.integrations.quercus import _cached_paginated_get
        with patch("api.integrations.quercus.requests.get", return_value=_mock_response({}, 401)):
            with pytest.raises(QuercusAuthError):
                _cached_paginated_get("tok", "/courses")
        bad = _mock_response({}, 500)
        bad.text = "server exploded"
        with patch("api.integrations.quercus.requests.get", return_value=bad):
            with pytest.raises(QuercusError):
                _cached_paginated_get("tok", "/courses")

    def test_cached_paginated_get_accumulates_pages(self):
        from api.integrations.quercus import _cached_paginated_get
        resp1 = _mock_response([{"id": 1}], link_header='<https://q.utoronto.ca/api/v1/courses?page=2>; rel="next"')
        resp2 = _mock_response([{"id": 2}])
        with patch("api.integrations.quercus.requests.get", side_effect=[resp1, resp2]):
            result = _cached_paginated_get("tok", "/courses")
        assert result == [{"id": 1}, {"id": 2}]

    def test_parse_canvas_datetime_handles_none(self):
        assert QuercusClient._parse_canvas_datetime(None) is None

    def test_get_file_metadata_and_modules_delegate_to_get(self):
        with patch.object(QuercusClient, "_get", side_effect=[{"id": 9}, [{"id": 1}]]) as mock_get:
            client = QuercusClient(token="tok")
            assert client.get_file_metadata(9)["id"] == 9
            assert client.get_course_modules(1) == [{"id": 1}]
        assert mock_get.call_count == 2

    def test_get_grades_returns_first_enrollment(self):
        with patch.object(QuercusClient, "_get", return_value=[{"id": "enr-1", "current_score": 80.0}]):
            client = QuercusClient(token="tok")
            result = client.get_grades(1)
        assert result["id"] == "enr-1"

    def test_get_latest_announcements_empty_courses_short_circuit(self):
        client = QuercusClient(token="tok")
        with patch.object(QuercusClient, "_get") as mock_get:
            result = client.get_latest_announcements([])
        assert result == []
        mock_get.assert_not_called()

    def test_get_latest_announcements_builds_context_params(self):
        with patch.object(QuercusClient, "_get", return_value=[]) as mock_get:
            client = QuercusClient(token="tok")
            client.get_latest_announcements([1, 2], days_back=7)
        params = mock_get.call_args.kwargs["params"]
        assert ("context_codes[]", "course_1") in params
        assert ("context_codes[]", "course_2") in params
