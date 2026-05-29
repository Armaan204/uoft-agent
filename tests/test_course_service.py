"""
tests/test_course_service.py — unit tests for api/services/course_service.py.

All Quercus, Supabase, and Anthropic calls are mocked.
"""

import pytest
from unittest.mock import MagicMock, patch


# ── pure helpers ──────────────────────────────────────────────────────────────

class TestFormatTermName:
    def test_canvas_year_first_reordered(self):
        from api.services.course_service import _format_term_name
        assert _format_term_name({"name": "2025 Winter"}) == "Winter 2025"

    def test_already_named(self):
        from api.services.course_service import _format_term_name
        assert _format_term_name({"name": "Fall 2024"}) == "Fall 2024"

    def test_none_term(self):
        from api.services.course_service import _format_term_name
        assert _format_term_name(None) == ""

    def test_derives_season_from_start_at(self):
        from api.services.course_service import _format_term_name
        # September → Fall
        result = _format_term_name({"name": "", "start_at": "2024-09-01T00:00:00Z"})
        assert result == "Fall 2024"

    def test_summer_from_start_at(self):
        from api.services.course_service import _format_term_name
        result = _format_term_name({"name": "", "start_at": "2024-06-01T00:00:00Z"})
        assert result == "Summer 2024"

    def test_winter_from_start_at(self):
        from api.services.course_service import _format_term_name
        result = _format_term_name({"name": "", "start_at": "2024-01-15T00:00:00Z"})
        assert result == "Winter 2024"

    def test_invalid_start_at_falls_back_to_empty(self):
        from api.services.course_service import _format_term_name
        assert _format_term_name({"name": "", "start_at": "not-a-date"}) == ""


class TestRiskFlag:
    def test_no_data_returns_no_breakdown(self):
        from api.services.course_service import _risk_flag
        assert _risk_flag(90.0, False) == "No breakdown"

    def test_below_70_at_risk(self):
        from api.services.course_service import _risk_flag
        assert _risk_flag(65.0, True) == "At risk"

    def test_between_70_and_85_on_track(self):
        from api.services.course_service import _risk_flag
        assert _risk_flag(78.0, True) == "On track"

    def test_above_85_safe(self):
        from api.services.course_service import _risk_flag
        assert _risk_flag(88.0, True) == "Safe"


class TestGradeFromPoints:
    def test_returns_zero_when_no_submissions(self):
        from api.services.course_service import _grade_from_points
        groups = [{"id": 1, "name": "Assignments", "rules": {}, "assignments": [
            {"id": 101, "name": "A1", "points_possible": 100}
        ]}]
        result = _grade_from_points(groups, [])
        assert result["weighted_grade"] == 0.0
        assert result["letter"] == "N/A"

    def test_computes_grade_from_points(self):
        from api.services.course_service import _grade_from_points
        groups = [{"id": 1, "name": "Midterm", "rules": {}, "assignments": [
            {"id": 101, "name": "Midterm", "points_possible": 100}
        ]}]
        submissions = [{"assignment_id": 101, "score": 80.0}]
        result = _grade_from_points(groups, submissions)
        assert result["weighted_grade"] == pytest.approx(80.0)

    def test_merges_duplicate_group_names(self):
        from api.services.course_service import _grade_from_points
        groups = [
            {"name": "Assignments", "assignments": [{"id": 1, "points_possible": 50}]},
            {"name": "Assignments", "assignments": [{"id": 2, "points_possible": 50}]},
        ]
        submissions = [{"assignment_id": 1, "score": 40.0}, {"assignment_id": 2, "score": 50.0}]
        result = _grade_from_points(groups, submissions)
        assert result["group_breakdown"]["Assignments"]["earned"] == 90.0


# ── _extract_uoft_code ───────────────────────────────────────────────────────

class TestExtractUoftCode:
    def test_plain_code_returned_unchanged(self):
        from api.services.course_service import _extract_uoft_code
        assert _extract_uoft_code("ARC181H1") == "ARC181H1"

    def test_strips_trailing_section_label(self):
        from api.services.course_service import _extract_uoft_code
        assert _extract_uoft_code("ARC181H1 Studio") == "ARC181H1"

    def test_strips_lecture_suffix(self):
        from api.services.course_service import _extract_uoft_code
        assert _extract_uoft_code("JAV101H1 Lecture") == "JAV101H1"

    def test_utsc_format(self):
        from api.services.course_service import _extract_uoft_code
        assert _extract_uoft_code("CSCA08H3") == "CSCA08H3"

    def test_st_george_format(self):
        from api.services.course_service import _extract_uoft_code
        assert _extract_uoft_code("CSC490H1") == "CSC490H1"

    def test_fallback_for_non_matching_code(self):
        from api.services.course_service import _extract_uoft_code
        assert _extract_uoft_code("SomeOtherCode") == "SomeOtherCode"


# ── list_current_term_courses ─────────────────────────────────────────────────

class TestListCurrentTermCourses:
    def test_returns_mapped_courses(self):
        from api.services.course_service import list_current_term_courses
        fake_courses = [
            {"id": 1, "name": "Intro CS", "course_code": "CSCA08H3", "term": {"name": "2025 Fall"}},
            {"id": 2, "name": "Calculus", "course_code": "MATA30H3", "term": {"name": "2025 Fall"}},
        ]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient:
            MockClient.return_value.get_courses.return_value = fake_courses
            result = list_current_term_courses("fake-token")

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["course_code"] == "CSCA08H3"
        assert result[0]["canvas_ids"] == [1]
        assert "term" in result[0]

    def test_returns_empty_list_when_no_courses(self):
        from api.services.course_service import list_current_term_courses
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient:
            MockClient.return_value.get_courses.return_value = []
            result = list_current_term_courses("fake-token")
        assert result == []

    def test_groups_duplicate_codes_and_keeps_lowest_id(self):
        """Duplicate course codes collect all canvas_ids; lowest id is canonical."""
        from api.services.course_service import list_current_term_courses
        fake_courses = [
            {"id": 200, "name": "ARC181H1 Lecture", "course_code": "ARC181H1", "term": {"name": "2026 Winter"}},
            {"id": 100, "name": "ARC181H1 Studio", "course_code": "ARC181H1", "term": {"name": "2026 Winter"}},
            {"id": 50, "name": "JAV101H1", "course_code": "JAV101H1", "term": {"name": "2026 Winter"}},
        ]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient:
            MockClient.return_value.get_courses.return_value = fake_courses
            result = list_current_term_courses("fake-token")

        assert len(result) == 2
        codes = [r["course_code"] for r in result]
        assert "ARC181H1" in codes
        assert "JAV101H1" in codes
        arc_entry = next(r for r in result if r["course_code"] == "ARC181H1")
        assert arc_entry["id"] == 100           # lowest canvas_id is canonical
        assert set(arc_entry["canvas_ids"]) == {100, 200}   # both IDs collected
        jav_entry = next(r for r in result if r["course_code"] == "JAV101H1")
        assert jav_entry["canvas_ids"] == [50]

    def test_groups_differing_raw_codes_that_share_uoft_code(self):
        """Canvas returns 'ARC181H1' and 'ARC181H1 Studio' — both normalize to ARC181H1."""
        from api.services.course_service import list_current_term_courses
        fake_courses = [
            {"id": 200, "name": "ARC181H1 Lecture", "course_code": "ARC181H1", "term": {"name": "2026 Winter"}},
            {"id": 100, "name": "ARC181H1 Studio", "course_code": "ARC181H1 Studio", "term": {"name": "2026 Winter"}},
        ]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient:
            MockClient.return_value.get_courses.return_value = fake_courses
            result = list_current_term_courses("fake-token")

        assert len(result) == 1
        assert result[0]["course_code"] == "ARC181H1"
        assert result[0]["id"] == 100           # lowest canvas_id is canonical
        assert set(result[0]["canvas_ids"]) == {100, 200}

    def test_courses_without_code_are_kept_as_is(self):
        """Courses with no course_code bypass deduplication and get a canvas_ids list."""
        from api.services.course_service import list_current_term_courses
        fake_courses = [
            {"id": 1, "name": "Course A", "course_code": None, "term": {}},
            {"id": 2, "name": "Course B", "course_code": None, "term": {}},
        ]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient:
            MockClient.return_value.get_courses.return_value = fake_courses
            result = list_current_term_courses("fake-token")
        assert len(result) == 2
        assert result[0]["canvas_ids"] == [1]
        assert result[1]["canvas_ids"] == [2]


# ── _merge_groups_and_submissions ────────────────────────────────────────────

class TestMergeGroupsAndSubmissions:
    def _make_group(self, group_id, name, assignments):
        return {"id": group_id, "name": name, "group_weight": 0.0, "rules": {}, "assignments": assignments}

    def _make_assignment(self, assignment_id, name, points=100):
        return {"id": assignment_id, "name": name, "points_possible": points}

    def _make_sub(self, assignment_id, score):
        return {"assignment_id": assignment_id, "score": score}

    def test_single_course_passthrough(self):
        from api.services.course_service import _merge_groups_and_submissions
        groups = [self._make_group(1, "Assignments", [self._make_assignment(10, "A1")])]
        subs = [self._make_sub(10, 80.0)]
        merged_groups, merged_subs = _merge_groups_and_submissions([groups], [subs])
        assert len(merged_groups) == 1
        assert len(merged_subs) == 1
        assert merged_subs[0]["score"] == 80.0

    def test_graded_beats_ungraded_for_same_assignment(self):
        from api.services.course_service import _merge_groups_and_submissions
        # Course 1: A1 ungraded; Course 2: A1 graded at 82
        g1 = [self._make_group(1, "G1", [self._make_assignment(10, "A1")])]
        s1 = []
        g2 = [self._make_group(2, "G2", [self._make_assignment(20, "A1")])]
        s2 = [self._make_sub(20, 82.0)]
        merged_groups, merged_subs = _merge_groups_and_submissions([g1, s1, g2, s2][::2], [g1, s1, g2, s2][1::2])
        assert len(merged_subs) == 1
        assert merged_subs[0]["score"] == 82.0

    def test_lower_score_wins_when_both_graded(self):
        from api.services.course_service import _merge_groups_and_submissions
        g1 = [self._make_group(1, "G1", [self._make_assignment(10, "A1")])]
        s1 = [self._make_sub(10, 95.0)]
        g2 = [self._make_group(2, "G2", [self._make_assignment(20, "A1")])]
        s2 = [self._make_sub(20, 82.0)]
        merged_groups, merged_subs = _merge_groups_and_submissions([g1, g2], [s1, s2])
        assert len(merged_subs) == 1
        assert merged_subs[0]["score"] == 82.0

    def test_unique_assignments_from_secondary_go_to_supplemental_group(self):
        from api.services.course_service import _merge_groups_and_submissions
        # Course 1 (primary, 2 graded): A1 at 90, A2 at 80
        # Course 2 (secondary, 2 graded, tie→idx 0 wins): A1 at 85 (lower wins), A3 at 70 (unique→supplemental)
        g1 = [self._make_group(1, "G1", [
            self._make_assignment(10, "A1"),
            self._make_assignment(11, "A2"),
        ])]
        s1 = [self._make_sub(10, 90.0), self._make_sub(11, 80.0)]
        g2 = [self._make_group(2, "G2", [
            self._make_assignment(20, "A1"),
            self._make_assignment(21, "A3"),
        ])]
        s2 = [self._make_sub(20, 85.0), self._make_sub(21, 70.0)]
        merged_groups, merged_subs = _merge_groups_and_submissions([g1, g2], [s1, s2])
        group_names = [g["name"] for g in merged_groups]
        # A3 only exists in secondary (Course 2) → lands in the supplemental group
        assert "Additional Assessments" in group_names
        supplemental = next(g for g in merged_groups if g["name"] == "Additional Assessments")
        assert any(a["name"] == "A3" for a in supplemental["assignments"])
        # Lower score wins for A1 (85 beats 90)
        assert any(s["score"] == 85.0 for s in merged_subs)

    def test_primary_is_course_with_most_grades(self):
        from api.services.course_service import _merge_groups_and_submissions
        # Course 0: no grades; Course 1: 2 graded → should be primary (its group structure used)
        g0 = [self._make_group(99, "PrimaryLecture", [self._make_assignment(1, "Q1")])]
        s0 = []
        g1 = [
            self._make_group(11, "Studio", [self._make_assignment(10, "A1")]),
            self._make_group(12, "Studio2", [self._make_assignment(11, "A2")]),
        ]
        s1 = [self._make_sub(10, 80.0), self._make_sub(11, 75.0)]
        merged_groups, merged_subs = _merge_groups_and_submissions([g0, g1], [s0, s1])
        # Primary is g1 (2 graded); g0's unique assignment Q1 goes to supplemental
        primary_group_names = [g["name"] for g in merged_groups if g["name"] != "Additional Assessments"]
        assert "Studio" in primary_group_names
        supplemental = next((g for g in merged_groups if g["name"] == "Additional Assessments"), None)
        assert supplemental is not None
        assert any(a["name"] == "Q1" for a in supplemental["assignments"])

    def test_case_and_whitespace_insensitive_dedup(self):
        from api.services.course_service import _merge_groups_and_submissions
        g1 = [self._make_group(1, "G1", [self._make_assignment(10, "  Assignment 1 ")])]
        s1 = [self._make_sub(10, 88.0)]
        g2 = [self._make_group(2, "G2", [self._make_assignment(20, "assignment 1")])]
        s2 = [self._make_sub(20, 72.0)]
        _, merged_subs = _merge_groups_and_submissions([g1, g2], [s1, s2])
        # Only one submission, lower score wins
        assert len(merged_subs) == 1
        assert merged_subs[0]["score"] == 72.0


# ── _resolve_weights_for_canvas_ids ──────────────────────────────────────────

class TestResolveWeightsForCanvasIds:
    def test_returns_first_valid_weights(self):
        from api.services.course_service import _resolve_weights_for_canvas_ids
        mock_client = MagicMock()
        with patch("api.services.course_service._resolve_course_weights_uncached") as mock_resolve:
            mock_resolve.side_effect = [
                (None, None),                          # first id: no weights
                ({"Assignments": 100.0}, "canvas"),    # second id: weights found
            ]
            weights, source = _resolve_weights_for_canvas_ids([1, 2], mock_client)
        assert weights == {"Assignments": 100.0}
        assert source == "canvas"

    def test_returns_none_when_all_ids_have_no_weights(self):
        from api.services.course_service import _resolve_weights_for_canvas_ids
        mock_client = MagicMock()
        with patch("api.services.course_service._resolve_course_weights_uncached", return_value=(None, None)):
            weights, source = _resolve_weights_for_canvas_ids([1, 2, 3], mock_client)
        assert weights is None
        assert source is None


# ── get_dashboard_course ──────────────────────────────────────────────────────

class TestGetDashboardCourse:
    def _course(self):
        return {
            "id": 1001,
            "name": "Intro CS",
            "course_code": "CSCA08H3",
            "term": {"name": "2025 Fall"},
        }

    def _groups(self):
        return [{"id": 10, "name": "Assignments", "group_weight": 100.0,
                 "rules": {}, "assignments": [
                     {"id": 101, "name": "A1", "points_possible": 100}
                 ]}]

    def _submissions(self):
        return [{"assignment_id": 101, "score": 85.0}]

    def test_returns_course_dict_with_canvas_weights(self):
        from api.services.course_service import get_dashboard_course
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._resolve_course_weights_uncached",
                   return_value=({"Assignments": 100.0}, "canvas")):

            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = self._groups()
            mock_c.get_submissions.return_value = self._submissions()
            mock_c.get_assignments.return_value = []

            result = get_dashboard_course("tok", self._course())

        assert result["id"] == 1001
        assert result["course_code"] == "CSCA08H3"
        assert "current_grade" in result
        assert "letter_grade" in result

    def test_returns_course_dict_without_weights(self):
        """When no weights are resolved, falls back to raw point-based grade."""
        from api.services.course_service import get_dashboard_course
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._resolve_course_weights_uncached",
                   return_value=(None, None)):

            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = self._groups()
            mock_c.get_submissions.return_value = self._submissions()
            mock_c.get_assignments.return_value = []

            result = get_dashboard_course("tok", self._course())

        assert "current_grade" in result
        assert result["risk_flag"] is not None

    def test_unreliable_component_model_falls_back_to_points(self):
        from api.services.course_service import get_dashboard_course
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._resolve_course_weights_uncached", return_value=({"Assignments": 100.0}, "canvas")), \
             patch("api.services.course_service._calc.build_weighted_components", return_value={"reliable": False, "components": []}):
            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = self._groups()
            mock_c.get_submissions.return_value = self._submissions()
            mock_c.get_assignments.return_value = []
            result = get_dashboard_course("tok", self._course())
        assert result["display_grade"] == result["current_grade"]

    def test_merged_path_used_when_multiple_canvas_ids(self):
        """When a course has multiple canvas_ids, merged groups/submissions are used."""
        from api.services.course_service import get_dashboard_course
        course = {
            "id": 1001,
            "name": "Design Studio",
            "course_code": "JAV101H1",
            "term": {"name": "2026 Winter"},
            "canvas_ids": [1001, 2002],
        }
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._merge_groups_and_submissions",
                   return_value=(self._groups(), self._submissions())) as mock_merge, \
             patch("api.services.course_service._resolve_weights_for_canvas_ids",
                   return_value=({"Assignments": 100.0}, "canvas")):
            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = self._groups()
            mock_c.get_submissions.return_value = self._submissions()
            mock_c.get_assignments.return_value = []
            result = get_dashboard_course("tok", course)

        mock_merge.assert_called_once()
        assert result["canvas_ids"] == [1001, 2002]
        assert result["id"] == 1001

    def test_canvas_ids_in_response_for_single_course(self):
        """canvas_ids is always present in the dashboard response."""
        from api.services.course_service import get_dashboard_course
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._resolve_course_weights_uncached",
                   return_value=(None, None)):
            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = self._groups()
            mock_c.get_submissions.return_value = self._submissions()
            mock_c.get_assignments.return_value = []
            result = get_dashboard_course("tok", self._course())

        assert result["canvas_ids"] == [1001]


# ── get_course_weights ────────────────────────────────────────────────────────

class TestGetCourseWeights:
    def test_returns_canvas_weights(self):
        from api.services.course_service import get_course_weights
        with patch("api.services.course_service.UncachedQuercusClient"), \
             patch("api.services.course_service._resolve_course_weights_uncached",
                   return_value=({"Final": 60.0, "Midterm": 40.0}, "canvas")):
            result = get_course_weights("tok", 1001)

        assert result["weights_source"] == "canvas"
        assert result["weights"]["Final"] == 60.0

    def test_returns_empty_weights_when_none_found(self):
        from api.services.course_service import get_course_weights
        with patch("api.services.course_service.UncachedQuercusClient"), \
             patch("api.services.course_service._resolve_course_weights_uncached",
                   return_value=(None, None)):
            result = get_course_weights("tok", 1001)

        assert result["weights"] == {}
        assert result["weights_source"] is None


# ── get_course_grades ─────────────────────────────────────────────────────────

class TestGetCourseGrades:
    def _groups(self):
        return [{"id": 10, "name": "Midterm", "group_weight": 40.0,
                 "rules": {}, "assignments": [
                     {"id": 101, "name": "Midterm Exam", "points_possible": 100}
                 ]}]

    def _submissions(self):
        return [{"assignment_id": 101, "score": 75.0}]

    def test_returns_grades_dict_with_weights(self):
        from api.services.course_service import get_course_grades
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._resolve_course_weights_uncached",
                   return_value=({"Midterm": 40.0}, "canvas")), \
             patch("api.services.course_service.get_saved_grades", return_value={}), \
             patch("api.services.course_service.get_grade_overrides", return_value={}), \
             patch("api.services.course_service.detect_new_grades", return_value=[]):

            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = self._groups()
            mock_c.get_submissions.return_value = self._submissions()
            mock_c.get_grades.return_value = {}

            result = get_course_grades("tok", 1001, user_id="u1")

        assert result["course_id"] == 1001
        assert "grade" in result
        assert "weights" in result

    def test_returns_grades_dict_without_weights(self):
        from api.services.course_service import get_course_grades
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
            patch("api.services.course_service._resolve_course_weights_uncached",
                   return_value=(None, None)), \
             patch("api.services.course_service.get_saved_grades", return_value={}), \
             patch("api.services.course_service.get_grade_overrides", return_value={}), \
             patch("api.services.course_service.detect_new_grades", return_value=[]):

            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = self._groups()
            mock_c.get_submissions.return_value = self._submissions()
            mock_c.get_grades.return_value = {}

            result = get_course_grades("tok", 1001)

        assert result["weights"] == {}
        assert result["components"] == []

    def test_applies_drop_rules_in_component_model(self):
        from api.services.course_service import get_course_grades
        groups = [{
            "id": 10,
            "name": "Quizzes",
            "group_weight": 100.0,
            "rules": {"drop_lowest": 1},
            "assignments": [
                {"id": 101, "name": "Q1", "points_possible": 10},
                {"id": 102, "name": "Q2", "points_possible": 10},
            ],
        }]
        submissions = [
            {"assignment_id": 101, "score": 2.0},
            {"assignment_id": 102, "score": 10.0},
        ]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._resolve_course_weights_uncached", return_value=({"Quizzes": 100.0}, "canvas")):
            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = groups
            mock_c.get_submissions.return_value = submissions
            mock_c.get_grades.return_value = {}
            result = get_course_grades("tok", 1001)
        assert result["grade"]["weighted_grade"] == pytest.approx(100.0)
        assert result["component_model"]["dropped_assignment_ids"] == [101]


class TestCourseOverrideFlows:
    def test_save_course_grade_overrides_uses_cached_snapshot(self):
        from api.services.course_service import save_course_grade_overrides
        snapshot = {
            "live_components": [{"component_key": "mid", "status": "graded", "possible": 100.0, "earned": 70.0, "pct": 70.0, "weight": 100.0, "name": "Midterm"}],
            "component_model": {"reliable": True, "components": []},
            "weights": {"Midterm": 100.0},
            "weights_source": "canvas",
            "enrollment": {},
        }
        with patch("api.services.course_service.save_grade_override") as mock_save_override, \
             patch("api.services.course_service.save_grades"), \
             patch("api.services.course_service.get_grade_overrides", return_value={"mid": {"manual_score": 90.0, "manual_possible": 100.0}}), \
             patch("api.services.course_service.get_saved_grades", return_value={}), \
             patch("api.services.course_service.detect_new_grades", return_value=[]):
            result = save_course_grade_overrides("tok", "u1", 1, [{"component_key": "mid", "manual_score": 90.0, "manual_possible": 100.0}], snapshot)
        mock_save_override.assert_called_once()
        assert result["components"][0]["is_manual"] is True

    def test_save_course_grade_overrides_rejects_mismatched_possible(self):
        from api.services.course_service import save_course_grade_overrides, CourseServiceError
        snapshot = {
            "live_components": [{"component_key": "mid", "status": "graded", "possible": 100.0, "earned": 70.0, "pct": 70.0, "weight": 100.0, "name": "Midterm"}],
            "component_model": {"reliable": True, "components": []},
            "weights": {"Midterm": 100.0},
            "weights_source": "canvas",
            "enrollment": {},
        }
        with pytest.raises(CourseServiceError, match="points possible do not match"):
            save_course_grade_overrides("tok", "u1", 1, [{"component_key": "mid", "manual_score": 90.0, "manual_possible": 50.0}], snapshot)

    def test_delete_course_grade_override_uses_cached_snapshot(self):
        from api.services.course_service import delete_course_grade_override
        snapshot = {
            "live_components": [{"component_key": "mid", "status": "graded", "possible": 100.0, "earned": 70.0, "pct": 70.0, "weight": 100.0, "name": "Midterm"}],
            "component_model": {"reliable": True, "components": []},
        }
        with patch("api.services.course_service.delete_grade_override"), \
             patch("api.services.course_service.get_grade_overrides", return_value={}):
            result = delete_course_grade_override("tok", "u1", 1, "mid", snapshot)
        assert result["overrides"] == {}

    def test_delete_course_grade_override_falls_back_to_live_fetch(self):
        from api.services.course_service import delete_course_grade_override
        with patch("api.services.course_service.delete_grade_override"), \
             patch("api.services.course_service.get_course_grades", return_value={"course_id": 1}) as mock_live:
            result = delete_course_grade_override("tok", "u1", 1, "mid", None)
        mock_live.assert_called_once()
        assert result["course_id"] == 1


# ── get_dashboard_announcements ───────────────────────────────────────────────

class TestGetDashboardAnnouncements:
    def _courses(self):
        return [{"id": 1001, "name": "Intro CS", "course_code": "CSCA08H3"}]

    def test_returns_mapped_announcements(self):
        from api.services.course_service import get_dashboard_announcements
        fake_raw = [{
            "context_code": "course_1001",
            "title": "Midterm reminder",
            "message": "<p>Don't forget the midterm.</p>",
            "html_url": "https://q.utoronto.ca/ann/1",
            "posted_at": "2024-10-01T10:00:00Z",
        }]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient:
            MockClient.return_value.get_latest_announcements.return_value = fake_raw
            result = get_dashboard_announcements("tok", self._courses())

        assert len(result) == 1
        assert result[0]["course_id"] == 1001
        assert result[0]["title"] == "Midterm reminder"

    def test_skips_non_course_context(self):
        from api.services.course_service import get_dashboard_announcements
        fake_raw = [{"context_code": "group_123", "title": "Skip me"}]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient:
            MockClient.return_value.get_latest_announcements.return_value = fake_raw
            result = get_dashboard_announcements("tok", self._courses())
        assert result == []

    def test_skips_unknown_course_id(self):
        from api.services.course_service import get_dashboard_announcements
        fake_raw = [{"context_code": "course_9999", "title": "Unknown course"}]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient:
            MockClient.return_value.get_latest_announcements.return_value = fake_raw
            result = get_dashboard_announcements("tok", self._courses())
        assert result == []

    def test_handles_invalid_posted_at(self):
        from api.services.course_service import get_dashboard_announcements
        fake_raw = [{
            "context_code": "course_1001",
            "title": "Bad date",
            "message": "text",
            "html_url": "https://q.utoronto.ca/ann/2",
            "posted_at": "not-a-date",
        }]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient:
            MockClient.return_value.get_latest_announcements.return_value = fake_raw
            result = get_dashboard_announcements("tok", self._courses())
        assert result[0]["posted_at"] is None

    def test_skips_invalid_course_id_suffix(self):
        from api.services.course_service import get_dashboard_announcements
        fake_raw = [{"context_code": "course_notanint", "title": "Bad context"}]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient:
            MockClient.return_value.get_latest_announcements.return_value = fake_raw
            result = get_dashboard_announcements("tok", self._courses())
        assert result == []


# ── get_latest_course_announcement ────────────────────────────────────────────

class TestGetLatestCourseAnnouncement:
    def test_returns_announcement_dict(self):
        from api.services.course_service import get_latest_course_announcement
        fake_raw = [{
            "context_code": "course_1001",
            "title": "Quiz next week",
            "message": "<p>Be prepared.</p>",
            "html_url": "https://q.utoronto.ca/ann/3",
            "posted_at": "2024-10-05T09:00:00Z",
        }]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient:
            MockClient.return_value.get_latest_announcements.return_value = fake_raw
            result = get_latest_course_announcement("tok", 1001)

        assert result["course_id"] == 1001
        assert result["title"] == "Quiz next week"
        assert "body_html" in result

    def test_raises_when_no_matching_announcement(self):
        from api.services.course_service import get_latest_course_announcement, CourseServiceError
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient:
            MockClient.return_value.get_latest_announcements.return_value = []
            with pytest.raises(CourseServiceError):
                get_latest_course_announcement("tok", 1001)

    def test_skips_wrong_course_context(self):
        from api.services.course_service import get_latest_course_announcement, CourseServiceError
        fake_raw = [{"context_code": "course_9999", "title": "Wrong course"}]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient:
            MockClient.return_value.get_latest_announcements.return_value = fake_raw
            with pytest.raises(CourseServiceError):
                get_latest_course_announcement("tok", 1001)

    def test_handles_invalid_posted_at_in_latest_announcement(self):
        from api.services.course_service import get_latest_course_announcement
        fake_raw = [{
            "context_code": "course_1001",
            "title": "Bad date",
            "message": "<p>x</p>",
            "posted_at": "not-a-date",
        }]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient:
            MockClient.return_value.get_latest_announcements.return_value = fake_raw
            result = get_latest_course_announcement("tok", 1001)
        assert result["posted_at"] is None


# ── get_course_scenarios ──────────────────────────────────────────────────────

class TestGetCourseScenarios:
    def _groups(self):
        return [{"id": 10, "name": "Final Exam", "rules": {}, "assignments": [
            {"id": 101, "name": "Final", "points_possible": 100}
        ]}]

    def _submissions_none(self):
        return []  # no score yet → ungraded

    def test_returns_scenarios_for_ungraded_group(self):
        from api.services.course_service import get_course_scenarios
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._resolve_course_weights_uncached",
                   return_value=({"Final Exam": 60.0}, "canvas")):
            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = self._groups()
            mock_c.get_submissions.return_value = self._submissions_none()
            result = get_course_scenarios("tok", 1001)

        assert result["course_id"] == 1001
        assert "scenarios" in result
        assert result["final_assessment"] == "Final Exam"

    def test_raises_when_no_weights(self):
        from api.services.course_service import get_course_scenarios, CourseServiceError
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._resolve_course_weights_uncached",
                   return_value=(None, None)):
            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = self._groups()
            mock_c.get_submissions.return_value = self._submissions_none()
            with pytest.raises(CourseServiceError):
                get_course_scenarios("tok", 1001)

    def test_returns_no_ungraded_error_when_all_graded(self):
        from api.services.course_service import get_course_scenarios
        graded_submissions = [{"assignment_id": 101, "score": 80.0}]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._resolve_course_weights_uncached",
                   return_value=({"Final Exam": 60.0}, "canvas")):
            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = self._groups()
            mock_c.get_submissions.return_value = graded_submissions
            result = get_course_scenarios("tok", 1001)

        assert "error" in result
        assert result["scenarios"] == {}

    def test_returns_impossible_needed_score(self):
        from api.services.course_service import get_course_scenarios
        groups = [
            {
                "id": 1,
                "name": "Midterm",
                "rules": {},
                "assignments": [{"id": 10, "name": "Midterm", "points_possible": 100}],
            },
            {
                "id": 2,
                "name": "Final Exam",
                "rules": {},
                "assignments": [{"id": 11, "name": "Final", "points_possible": 100}],
            },
        ]
        submissions = [{"assignment_id": 10, "score": 10.0}]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._resolve_course_weights_uncached", return_value=({"Midterm": 60.0, "Final Exam": 40.0}, "canvas")):
            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = groups
            mock_c.get_submissions.return_value = submissions
            result = get_course_scenarios("tok", 1001)
        assert result["scenarios"]["A+"]["status"] == "impossible"

    def test_returns_already_achieved_when_no_remaining_weight(self):
        from api.services.course_service import get_course_scenarios
        groups = [
            {
                "id": 1,
                "name": "Midterm",
                "rules": {},
                "assignments": [{"id": 10, "name": "Midterm", "points_possible": 100}],
            },
            {
                "id": 2,
                "name": "Final Exam",
                "rules": {},
                "assignments": [{"id": 11, "name": "Final", "points_possible": 100}],
            },
        ]
        submissions = [{"assignment_id": 10, "score": 100.0}]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._resolve_course_weights_uncached", return_value=({"Midterm": 100.0, "Final Exam": 0.0}, "canvas")):
            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = groups
            mock_c.get_submissions.return_value = submissions
            result = get_course_scenarios("tok", 1001)
        assert result["final_weight_pct"] == 0.0
        assert all(item["status"] == "already_achieved" for item in result["scenarios"].values())


# ── _resolve_course_weights_uncached ──────────────────────────────────────────

class TestResolveCourseWeightsUncached:
    def test_returns_canvas_weights_when_available(self):
        from api.services.course_service import _resolve_course_weights_uncached
        mock_client = MagicMock()
        mock_client.get_canvas_weights.return_value = {"Midterm": 40.0, "Final": 60.0}
        weights, source = _resolve_course_weights_uncached(1001, mock_client)
        assert weights == {"Midterm": 40.0, "Final": 60.0}
        assert source == "canvas"

    def test_falls_back_to_syllabus_when_no_canvas_weights(self):
        from api.services.course_service import _resolve_course_weights_uncached
        mock_client = MagicMock()
        mock_client.get_canvas_weights.return_value = None
        mock_client.get_syllabus.return_value = {"pdf_urls": [], "syllabus_body": "<p>Midterm 40%</p>"}
        with patch("api.services.course_service.parse_syllabus_weights_uncached",
                   return_value=("syllabus", {"Midterm": 40.0})):
            weights, source = _resolve_course_weights_uncached(1001, mock_client)
        assert source == "syllabus"
        assert weights == {"Midterm": 40.0}

    def test_returns_none_on_syllabus_error(self):
        from api.services.course_service import _resolve_course_weights_uncached
        from api.integrations.syllabus import SyllabusError
        mock_client = MagicMock()
        mock_client.get_canvas_weights.return_value = None
        mock_client.get_syllabus.side_effect = SyllabusError("not found")
        weights, source = _resolve_course_weights_uncached(1001, mock_client)
        assert weights is None
        assert source is None


class TestCourseServiceHelpers:
    def test_get_user_quercus_token_success(self):
        from api.services.course_service import get_user_quercus_token
        with patch("api.services.course_service.get_quercus_token", return_value="secret"):
            assert get_user_quercus_token("u1") == "secret"

    def test_get_user_quercus_token_raises_on_missing(self):
        from api.services.course_service import get_user_quercus_token, CourseServiceError
        with patch("api.services.course_service.get_quercus_token", return_value=None):
            with pytest.raises(CourseServiceError):
                get_user_quercus_token("u1")

    def test_get_upcoming_deadlines_filters_window(self):
        from api.services.course_service import _get_upcoming_deadlines
        client = MagicMock()
        client.get_assignments.return_value = [
            {"name": "Soon", "due_at": "2099-01-05T00:00:00Z", "html_url": "u1"},
            {"name": "No due date"},
        ]
        with patch("api.services.course_service.datetime") as mock_dt:
            from datetime import datetime, timezone
            now = datetime(2099, 1, 1, tzinfo=timezone.utc)
            mock_dt.now.return_value = now
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            deadlines = _get_upcoming_deadlines(client, 1, "CSCA08H3")
        assert deadlines[0]["name"] == "Soon"

    def test_announcement_preview_truncates(self):
        from api.services.course_service import _announcement_preview
        assert _announcement_preview("<p>" + ("x" * 200) + "</p>", limit=20).endswith("…")

    def test_sanitize_announcement_html_removes_unsafe_content(self):
        from api.services.course_service import _sanitize_announcement_html
        cleaned = _sanitize_announcement_html('<p onclick="x()">Hi</p><script>alert(1)</script><a href="javascript:bad()">x</a>')
        assert "onclick" not in cleaned
        assert "script" not in cleaned.lower()
        assert "javascript:" not in cleaned.lower()

    def test_parse_syllabus_weights_uncached_canvas_page_path(self):
        from api.services.course_service import parse_syllabus_weights_uncached
        client = MagicMock()
        client.get_page.return_value = {"body": "<p>content</p>"}
        with patch("api.services.course_service.find_syllabus_file", return_value=None), \
             patch("api.services.course_service.find_syllabus_frontpage", return_value=None), \
             patch("api.services.course_service.find_syllabus_page", return_value={"page_slug": "outline"}), \
             patch("api.services.course_service._load_persisted_weights", return_value=None), \
             patch("api.services.course_service._extract_text_from_html", return_value="text"), \
             patch("api.services.course_service._ask_claude", return_value={"Midterm": 50}), \
             patch("api.services.course_service._save_persisted_weights"):
            source, weights = parse_syllabus_weights_uncached(1, client)
        assert source == "canvas-page:outline"
        assert weights["Midterm"] == 50

    def test_parse_syllabus_weights_uncached_body_fallback(self):
        from api.services.course_service import parse_syllabus_weights_uncached
        client = MagicMock()
        with patch("api.services.course_service.find_syllabus_file", return_value=None), \
             patch("api.services.course_service.find_syllabus_frontpage", return_value=None), \
             patch("api.services.course_service.find_syllabus_page", return_value=None), \
             patch("api.services.course_service._load_persisted_weights", return_value=None), \
             patch("api.services.course_service._extract_text_from_html", return_value="text"), \
             patch("api.services.course_service._ask_claude", return_value={"Final": 100}), \
             patch("api.services.course_service._save_persisted_weights"):
            source, weights = parse_syllabus_weights_uncached(1, client, syllabus_body_html="<p>Final</p>")
        assert source == "syllabus-body:1"
        assert weights["Final"] == 100

    def test_grade_from_components_zero_weight_returns_na(self):
        from api.services.course_service import _grade_from_components
        result = _grade_from_components([{"status": "ungraded", "weight": 100.0, "pct": None}])
        assert result["letter"] == "N/A"

    def test_apply_grade_overrides_ignores_zero_possible_override(self):
        from api.services.course_service import _apply_grade_overrides
        components = [{"name": "Final", "source": "group", "group_name": "Final", "status": "ungraded", "possible": None}]
        result = _apply_grade_overrides(components, {"group::final::final::ungraded::none": {"manual_score": 90.0, "manual_possible": 0}})
        assert result[0]["is_manual"] is False


class TestCourseServiceAdditional:
    def test_uncached_quercus_client_methods_delegate_to_get(self):
        from api.services.course_service import UncachedQuercusClient
        with patch.object(UncachedQuercusClient, "_get", side_effect=[[{"id": 1}], [{"id": 2}]]) as mock_get:
            client = UncachedQuercusClient(token="tok")
            assert client.get_submissions(1) == [{"id": 1}]
            assert client.get_assignment_groups(1) == [{"id": 2}]
        assert mock_get.call_count == 2

    def test_get_user_quercus_token_wraps_user_store_error(self):
        from api.services.course_service import get_user_quercus_token, CourseServiceError
        from api.auth.user_store import UserStoreError
        with patch("api.services.course_service.get_quercus_token", side_effect=UserStoreError("db down")):
            with pytest.raises(CourseServiceError, match="db down"):
                get_user_quercus_token("u1")

    def test_save_course_grade_overrides_rejects_unreliable_cached_snapshot(self):
        from api.services.course_service import save_course_grade_overrides, CourseServiceError
        snapshot = {
            "live_components": [{"component_key": "mid"}],
            "component_model": {"reliable": False, "components": []},
        }
        with pytest.raises(CourseServiceError, match="could not be mapped reliably"):
            save_course_grade_overrides("tok", "u1", 1, [], snapshot)

    def test_get_course_grades_with_weights_without_user_context(self):
        from api.services.course_service import get_course_grades
        groups = [{"id": 10, "name": "Midterm", "rules": {}, "assignments": [{"id": 101, "name": "Midterm", "points_possible": 100}]}]
        submissions = [{"assignment_id": 101, "score": 75.0}]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._resolve_course_weights_uncached", return_value=({"Midterm": 100.0}, "canvas")):
            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = groups
            mock_c.get_submissions.return_value = submissions
            mock_c.get_grades.return_value = {"current_score": 75.0}
            result = get_course_grades("tok", 1001, user_id=None)
        assert result["saved_grades"] == {}
        assert result["live_components"] == []

    def test_save_course_grade_overrides_live_fetch_requires_weights(self):
        from api.services.course_service import save_course_grade_overrides, CourseServiceError
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._resolve_course_weights_uncached", return_value=(None, None)):
            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = []
            mock_c.get_submissions.return_value = []
            with pytest.raises(CourseServiceError, match="No Canvas weights"):
                save_course_grade_overrides("tok", "u1", 1, [], None)

    def test_save_course_grade_overrides_live_fetch_rejects_unreliable_model(self):
        from api.services.course_service import save_course_grade_overrides, CourseServiceError
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._resolve_course_weights_uncached", return_value=({"Midterm": 100.0}, "canvas")), \
             patch("api.services.course_service._calc.build_weighted_components", return_value={"reliable": False, "components": []}):
            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = []
            mock_c.get_submissions.return_value = []
            with pytest.raises(CourseServiceError, match="could not be mapped reliably"):
                save_course_grade_overrides("tok", "u1", 1, [], None)

    def test_save_course_grade_overrides_validates_missing_key_and_nonpositive_possible(self):
        from api.services.course_service import save_course_grade_overrides, CourseServiceError
        snapshot = {
            "live_components": [{"component_key": "mid", "status": "ungraded", "possible": 0.0, "weight": 100.0, "name": "Midterm"}],
            "component_model": {"reliable": True, "components": []},
            "weights": {"Midterm": 100.0},
            "weights_source": "canvas",
            "enrollment": {},
        }
        with pytest.raises(CourseServiceError, match="component_key must be provided"):
            save_course_grade_overrides("tok", "u1", 1, [{"component_key": " ", "manual_score": 10.0, "manual_possible": 100.0}], snapshot)
        with pytest.raises(CourseServiceError, match="manual_possible must be greater than 0"):
            save_course_grade_overrides("tok", "u1", 1, [{"component_key": "mid", "manual_score": 10.0, "manual_possible": 0.0}], snapshot)

    def test_save_course_grade_overrides_rejects_missing_component_and_invalid_possible(self):
        from api.services.course_service import save_course_grade_overrides, CourseServiceError
        snapshot_missing = {
            "live_components": [{"component_key": "mid", "status": "ungraded", "possible": 0.0, "weight": 100.0, "name": "Midterm"}],
            "component_model": {"reliable": True, "components": []},
            "weights": {"Midterm": 100.0},
            "weights_source": "canvas",
            "enrollment": {},
        }
        with pytest.raises(CourseServiceError, match="Could not find a component"):
            save_course_grade_overrides("tok", "u1", 1, [{"component_key": "final", "manual_score": 10.0, "manual_possible": 100.0}], snapshot_missing)

        snapshot_bad_possible = {
            "live_components": [{"component_key": "mid", "status": "graded", "possible": 0.0, "weight": 100.0, "name": "Midterm"}],
            "component_model": {"reliable": True, "components": []},
            "weights": {"Midterm": 100.0},
            "weights_source": "canvas",
            "enrollment": {},
        }
        with pytest.raises(CourseServiceError, match="does not have a valid possible score"):
            save_course_grade_overrides("tok", "u1", 1, [{"component_key": "mid", "manual_score": 10.0, "manual_possible": 100.0}], snapshot_bad_possible)

    def test_save_course_grade_overrides_live_fetch_success_path(self):
        from api.services.course_service import save_course_grade_overrides
        mock_client = MagicMock()
        mock_client.get_assignment_groups.return_value = [{"id": 1, "name": "Midterm", "assignments": [{"id": 10, "name": "Midterm", "points_possible": 100}], "rules": {}}]
        mock_client.get_submissions.return_value = [{"assignment_id": 10, "score": 80.0}]
        mock_client.get_grades.return_value = {"current_score": 80.0, "current_grade": "A-", "final_score": None, "final_grade": None}

        with patch("api.services.course_service.UncachedQuercusClient", return_value=mock_client), \
             patch("api.services.course_service._resolve_course_weights_uncached", return_value=({"Midterm": 100.0}, "canvas")), \
             patch("api.services.course_service._calc.build_weighted_components", return_value={"reliable": True, "components": [{"component_key": "mid", "status": "graded", "possible": 100.0, "earned": 80.0, "pct": 80.0, "weight": 100.0, "name": "Midterm"}]}), \
             patch("api.services.course_service.save_grade_override") as mock_save_override, \
             patch("api.services.course_service.save_grades"), \
             patch("api.services.course_service.get_grade_overrides", return_value={}), \
             patch("api.services.course_service.get_saved_grades", return_value={}), \
             patch("api.services.course_service.detect_new_grades", return_value=[]):
            result = save_course_grade_overrides(
                "tok", "u1", 1,
                [{"component_key": "mid", "manual_score": 95.0, "manual_possible": 100.0}],
                None,
            )
        mock_save_override.assert_called_once()
        assert result["weights_source"] == "canvas"

    def test_get_course_scenarios_uses_substring_and_shortest_name_matching(self):
        from api.services.course_service import get_course_scenarios
        groups = [{"id": 1, "name": "Final Examination", "rules": {}, "assignments": [{"id": 11, "name": "Final", "points_possible": 100}]}]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._resolve_course_weights_uncached", return_value=({"Final": 40.0}, "canvas")):
            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = groups
            mock_c.get_submissions.return_value = []
            result = get_course_scenarios("tok", 1001)
        assert result["final_weight_pct"] == 40.0

        groups2 = [{"id": 1, "name": "final", "rules": {}, "assignments": []}]
        with patch("api.services.course_service.UncachedQuercusClient") as MockClient, \
             patch("api.services.course_service._resolve_course_weights_uncached", return_value=({"final exam": 40.0, "final project showcase": 60.0}, "canvas")):
            mock_c = MockClient.return_value
            mock_c.get_assignment_groups.return_value = groups2
            mock_c.get_submissions.return_value = []
            result = get_course_scenarios("tok", 1001)
        assert result["final_weight_pct"] == 40.0

    def test_resolve_course_weights_uncached_ignores_empty_syllabus_weights(self):
        from api.services.course_service import _resolve_course_weights_uncached
        mock_client = MagicMock()
        mock_client.get_canvas_weights.return_value = None
        mock_client.get_syllabus.return_value = {"pdf_urls": ["http://a/file.pdf"], "syllabus_body": None}
        with patch("api.services.course_service.parse_syllabus_weights_uncached", return_value=("syllabus", {})):
            weights, source = _resolve_course_weights_uncached(1001, mock_client)
        assert weights is None
        assert source is None

    def test_announcement_preview_short_and_text_helpers(self):
        from api.services.course_service import _announcement_preview, _announcement_text
        assert _announcement_preview("<p>Hi</p>", limit=20) == "Hi"
        assert _announcement_text("<p>Hello &amp; world</p>") == "Hello & world"

    def test_parse_syllabus_weights_uncached_cached_paths_and_pdf_path(self):
        from api.services.course_service import parse_syllabus_weights_uncached
        client = MagicMock()
        with patch("api.services.course_service.find_syllabus_file", return_value=None), \
             patch("api.services.course_service.find_syllabus_frontpage", return_value=None), \
             patch("api.services.course_service.find_syllabus_page", return_value={"page_slug": "outline"}), \
             patch("api.services.course_service._load_persisted_weights", return_value={"Midterm": 40.0}):
            source, weights = parse_syllabus_weights_uncached(1, client)
        assert source == "canvas-page:outline"
        assert weights == {"Midterm": 40.0}

        with patch("api.services.course_service.find_syllabus_file", return_value=None), \
             patch("api.services.course_service.find_syllabus_frontpage", return_value=None), \
             patch("api.services.course_service.find_syllabus_page", return_value=None), \
             patch("api.services.course_service._load_persisted_weights", return_value={"Final": 100.0}):
            source, weights = parse_syllabus_weights_uncached(1, client, syllabus_body_html="<p>Final</p>")
        assert source == "syllabus-body:1"
        assert weights == {"Final": 100.0}

        with patch("api.services.course_service._load_persisted_weights", return_value={"Assignments": 100.0}):
            source, weights = parse_syllabus_weights_uncached(1, client, pdf_url="http://a/file.pdf")
        assert source == "http://a/file.pdf"
        assert weights == {"Assignments": 100.0}

    def test_parse_syllabus_weights_uncached_pdf_pipeline_and_failure(self):
        from api.services.course_service import parse_syllabus_weights_uncached
        client = MagicMock()
        with patch("api.services.course_service._load_persisted_weights", return_value=None), \
             patch("api.services.course_service._download_pdf", return_value=b"bytes"), \
             patch("api.services.course_service._extract_text", return_value="text"), \
             patch("api.services.course_service._ask_claude", return_value={"Assignments": 100.0}), \
             patch("api.services.course_service._save_persisted_weights"):
            source, weights = parse_syllabus_weights_uncached(1, client, pdf_url="http://a/file.pdf")
        assert source == "http://a/file.pdf"
        assert weights == {"Assignments": 100.0}

        with patch("api.services.course_service.find_syllabus_file", return_value=None), \
             patch("api.services.course_service.find_syllabus_frontpage", return_value=None), \
             patch("api.services.course_service.find_syllabus_page", return_value=None):
            with pytest.raises(Exception):
                parse_syllabus_weights_uncached(1, client)

    def test_grade_from_points_and_component_key_helpers(self):
        from api.services.course_service import _grade_from_points, _fallback_component_key, _with_component_key
        groups = [{"name": "Assignments", "assignments": [{"id": 1, "points_possible": 100}]}]
        submissions = [{"assignment_id": 1, "score": 90.0}]
        result = _grade_from_points(groups, submissions)
        assert result["_total_earned"] == 90.0
        assert result["_total_possible"] == 100.0

        key = _fallback_component_key({"source": "group", "group_name": "Final::Exam", "name": "Final::Exam", "status": "ungraded", "possible": ""})
        assert "::" in key
        wrapped = _with_component_key({"name": "Final", "source": "group", "group_name": "Final", "status": "ungraded", "possible": None})
        assert wrapped["component_key"]

    def test_apply_grade_overrides_marks_manual_component(self):
        from api.services.course_service import _apply_grade_overrides
        components = [{"component_key": "mid", "name": "Midterm", "source": "group", "group_name": "Midterm", "status": "ungraded", "possible": None}]
        result = _apply_grade_overrides(components, {"mid": {"manual_score": 45.0, "manual_possible": 50.0}})
        assert result[0]["is_manual"] is True
        assert result[0]["status"] == "graded"
