"""
tests/test_graduation.py — unit tests for the graduation planning service.

check_graduation_progress() is pure Python after the data is loaded, so
tests run without any Supabase or Anthropic calls.  Mocking is only
needed for get_program_requirements(), which hits both.
"""

import pytest
from unittest.mock import patch, MagicMock

from integrations.graduation_service import (
    check_graduation_progress,
    _parse_dept_level,
    _matches_filter,
    _satisfies_via_exclusion,
    _slugify_utsc,
    _detect_campus,
    _match_required,
    _match_n_credits_list,
    _match_open_pool,
)


# ── helper unit tests ─────────────────────────────────────────────────────────

class TestParseDeptLevel:
    @pytest.mark.parametrize("code,expected", [
        ("CSCA08H3", ("CSC", "A")),
        ("CSCB20H3", ("CSC", "B")),
        ("STAC33H3", ("STA", "C")),
        ("MATD01H3", ("MAT", "D")),
        ("CSC300H1", ("CSC", "C")),  # St. George 300-level → C
        ("STA302H1", ("STA", "C")),
        ("MAT401H5", ("MAT", "D")),
        ("ECO100H1", ("ECO", "A")),
    ])
    def test_parses_course_codes(self, code, expected):
        assert _parse_dept_level(code) == expected

    def test_returns_none_for_short_codes(self):
        assert _parse_dept_level("CS") is None

    def test_returns_none_for_unknown_numeric_level(self):
        assert _parse_dept_level("CSC900H1") is None


class TestMatchesFilter:
    def test_passes_matching_dept_and_level(self):
        assert _matches_filter("CSCC09H3", {"CSC"}, {"C"}, set())

    def test_fails_wrong_dept(self):
        assert not _matches_filter("STAC33H3", {"CSC"}, {"C"}, set())

    def test_fails_wrong_level(self):
        assert not _matches_filter("CSCA08H3", {"CSC"}, {"C"}, set())

    def test_exclusion_set_blocks_match(self):
        assert not _matches_filter("STAC32H3", {"STA"}, {"C"}, {"STAC32H3"})


class TestSatisfiesViaExclusion:
    def test_taken_in_required_exclusion_list(self):
        excl = {"CSCA08H3": {"CSC108H1"}}
        assert _satisfies_via_exclusion("CSC108H1", "CSCA08H3", excl)

    def test_required_in_taken_exclusion_list(self):
        excl = {"CSC108H1": {"CSCA08H3"}}
        assert _satisfies_via_exclusion("CSC108H1", "CSCA08H3", excl)

    def test_same_code_returns_false(self):
        excl = {"CSCA08H3": {"CSCA08H3"}}
        assert not _satisfies_via_exclusion("CSCA08H3", "CSCA08H3", excl)

    def test_no_match_returns_false(self):
        assert not _satisfies_via_exclusion("CSCA08H3", "CSCA48H3", {})


class TestDetectCampus:
    def test_detects_utsc_by_default(self):
        assert _detect_campus("Computer Science Specialist") == "UTSC"

    def test_detects_utm(self):
        assert _detect_campus("Computer Science Major (UTM)") == "UTM"

    def test_detects_artsci(self):
        assert _detect_campus("Computer Science Major (St. George)") == "ARTSCI"


# ── check_graduation_progress ─────────────────────────────────────────────────

class TestCheckGraduationProgress:
    def test_fully_satisfied_required_course(self):
        """CSCA08H3 completed → required item satisfied."""
        reqs = {
            "program_credits_required": 0.5,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "core", "label": "Core", "section": "core",
                "credits_required": 0.5,
                "items": [{
                    "id": "csca08", "type": "required",
                    "courses": ["CSCA08H3"], "credits": 0.5, "label": "Intro CS",
                }],
            }],
        }
        acorn = {"terms": [{"term": "Fall 2023", "courses": [
            {"code": "CSCA08H3", "grade": "A", "mark": 85, "credits": 0.5}
        ]}]}
        result = check_graduation_progress(reqs, acorn)
        assert result["overall_status"] == "satisfied"
        assert result["credits_satisfied"] == pytest.approx(0.5)
        assert result["credits_remaining"] == 0.0

    def test_or_alternatives_first_match_satisfies(self):
        """MATA30H3 or MATA31H3 — taking MATA30H3 satisfies the item."""
        reqs = {
            "program_credits_required": 0.5,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "calc", "label": "Calculus", "section": "core",
                "credits_required": 0.5,
                "items": [{
                    "id": "calc_either", "type": "required",
                    "courses": ["MATA30H3", "MATA31H3"], "credits": 0.5,
                    "label": "Calculus I",
                }],
            }],
        }
        acorn = {"terms": [{"term": "Fall 2023", "courses": [
            {"code": "MATA30H3", "grade": "B+", "mark": 78, "credits": 0.5}
        ]}]}
        result = check_graduation_progress(reqs, acorn)
        assert result["overall_status"] == "satisfied"

    def test_or_alternatives_second_match_satisfies(self):
        """Taking the second alternative (MATA31H3) also satisfies the item."""
        reqs = {
            "program_credits_required": 0.5,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "calc", "label": "Calculus", "section": "core",
                "credits_required": 0.5,
                "items": [{
                    "id": "calc_either", "type": "required",
                    "courses": ["MATA30H3", "MATA31H3"], "credits": 0.5,
                    "label": "Calculus I",
                }],
            }],
        }
        acorn = {"terms": [{"term": "Fall 2023", "courses": [
            {"code": "MATA31H3", "grade": "A-", "mark": 81, "credits": 0.5}
        ]}]}
        result = check_graduation_progress(reqs, acorn)
        assert result["overall_status"] == "satisfied"

    def test_ipr_course_counted_as_in_progress(self):
        """IPR grade → in_progress, not satisfied."""
        reqs = {
            "program_credits_required": 0.5,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "sta", "label": "Stats", "section": "core",
                "credits_required": 0.5,
                "items": [{
                    "id": "stac32", "type": "required",
                    "courses": ["STAC32H3"], "credits": 0.5, "label": "Stats",
                }],
            }],
        }
        acorn = {"terms": [{"term": "Winter 2024", "courses": [
            {"code": "STAC32H3", "grade": "IPR", "mark": None, "credits": 0.5}
        ]}]}
        result = check_graduation_progress(reqs, acorn)
        assert result["overall_status"] == "in_progress"
        assert result["credits_satisfied"] == 0.0
        assert result["credits_in_progress"] == pytest.approx(0.5)
        groups = result["groups"]
        assert groups[0]["status"] == "in_progress"

    def test_failed_course_not_counted(self):
        """Grade F → course is not in completed set."""
        reqs = {
            "program_credits_required": 0.5,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "req", "label": "Req", "section": "core",
                "credits_required": 0.5,
                "items": [{
                    "id": "item1", "type": "required",
                    "courses": ["CSCA08H3"], "credits": 0.5, "label": "CS I",
                }],
            }],
        }
        acorn = {"terms": [{"term": "Fall 2023", "courses": [
            {"code": "CSCA08H3", "grade": "F", "mark": 40, "credits": 0.5}
        ]}]}
        result = check_graduation_progress(reqs, acorn)
        assert result["overall_status"] == "remaining"

    def test_n_credits_from_list_satisfied(self):
        """n_credits_from_list: taking STAC32H3 satisfies the 0.5 cr STA requirement."""
        reqs = {
            "program_credits_required": 0.5,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "sta_list", "label": "STA List", "section": "core",
                "credits_required": 0.5,
                "items": [{
                    "id": "sta_item", "type": "n_credits_from_list",
                    "credits_needed": 0.5,
                    "courses": ["STAC32H3", "STAC33H3"],
                    "label": "0.5 cr STA",
                }],
            }],
        }
        acorn = {"terms": [{"term": "Fall 2023", "courses": [
            {"code": "STAC32H3", "grade": "B", "mark": 75, "credits": 0.5}
        ]}]}
        result = check_graduation_progress(reqs, acorn)
        assert result["overall_status"] == "satisfied"

    def test_open_pool_matched_by_dept_and_level(self):
        """CSCC09H3 (CSC, C-level) satisfies a CSC C-level open_pool requirement."""
        reqs = {
            "program_credits_required": 0.5,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "upper", "label": "Upper CSC", "section": "core",
                "credits_required": 0.5,
                "items": [{
                    "id": "csc_c", "type": "open_pool",
                    "credits_needed": 0.5,
                    "label": "0.5 cr C-level CSC",
                    "filters": {"departments": ["CSC"], "levels": ["C"]},
                    "exclusions": [],
                }],
            }],
        }
        acorn = {"terms": [{"term": "Fall 2023", "courses": [
            {"code": "CSCC09H3", "grade": "A-", "mark": 82, "credits": 0.5}
        ]}]}
        result = check_graduation_progress(reqs, acorn)
        assert result["overall_status"] == "satisfied"

    def test_open_pool_wrong_level_not_matched(self):
        """CSCA08H3 (A-level) does NOT satisfy a C-level open_pool requirement."""
        reqs = {
            "program_credits_required": 0.5,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "upper", "label": "Upper CSC", "section": "core",
                "credits_required": 0.5,
                "items": [{
                    "id": "csc_c", "type": "open_pool",
                    "credits_needed": 0.5,
                    "label": "0.5 cr C-level CSC",
                    "filters": {"departments": ["CSC"], "levels": ["C"]},
                    "exclusions": [],
                }],
            }],
        }
        acorn = {"terms": [{"term": "Fall 2023", "courses": [
            {"code": "CSCA08H3", "grade": "A", "mark": 88, "credits": 0.5}
        ]}]}
        result = check_graduation_progress(reqs, acorn)
        assert result["overall_status"] == "remaining"

    def test_open_pool_partial_sub_requirement_satisfied_but_group_still_remaining(self):
        reqs = {
            "program_credits_required": 1.5,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "upper",
                "label": "Upper Pool",
                "section": "core",
                "credits_required": 1.5,
                "items": [{
                    "id": "pool",
                    "type": "open_pool",
                    "credits_needed": 1.5,
                    "label": "1.5 credits upper-year CSC/STA with 1.0 STA",
                    "filters": {"departments": ["CSC", "STA"], "levels": ["C"]},
                    "exclusions": [],
                    "sub_requirements": [{
                        "id": "sta_min",
                        "label": "1.0 STA",
                        "departments": ["STA"],
                        "levels": ["C"],
                        "min_credits": 1.0,
                    }],
                }],
            }],
        }
        acorn = {"terms": [{"term": "Fall 2023", "courses": [
            {"code": "STAC32H3", "grade": "A", "mark": 85, "credits": 0.5},
            {"code": "CSCC09H3", "grade": "A", "mark": 85, "credits": 0.5},
        ]}]}
        result = check_graduation_progress(reqs, acorn)
        item = result["groups"][0]["items"][0]
        assert item["status"] == "remaining"
        assert item["sub_requirements"][0]["status"] == "remaining"
        assert item["credits_satisfied"] == pytest.approx(1.0)

    def test_open_pool_exclusions_filter_out_otherwise_matching_courses(self):
        reqs = {
            "program_credits_required": 0.5,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "upper", "label": "Upper CSC", "section": "core", "credits_required": 0.5,
                "items": [{
                    "id": "pool",
                    "type": "open_pool",
                    "credits_needed": 0.5,
                    "label": "0.5 CSC C-level",
                    "filters": {"departments": ["CSC"], "levels": ["C"]},
                    "exclusions": ["CSCC09H3"],
                }],
            }],
        }
        acorn = {"terms": [{"term": "Fall 2023", "courses": [
            {"code": "CSCC09H3", "grade": "A", "mark": 85, "credits": 0.5},
        ]}]}
        result = check_graduation_progress(reqs, acorn)
        assert result["overall_status"] == "remaining"

    def test_n_credits_from_list_partially_satisfied(self):
        reqs = {
            "program_credits_required": 1.0,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "list", "label": "List", "section": "core", "credits_required": 1.0,
                "items": [{
                    "id": "item",
                    "type": "n_credits_from_list",
                    "credits_needed": 1.0,
                    "courses": ["STAC32H3", "STAC33H3", "STAC67H3"],
                    "label": "1.0 STA",
                }],
            }],
        }
        acorn = {"terms": [{"term": "Fall 2023", "courses": [
            {"code": "STAC32H3", "grade": "A", "mark": 80, "credits": 0.5},
        ]}]}
        result = check_graduation_progress(reqs, acorn)
        item = result["groups"][0]["items"][0]
        assert item["status"] == "remaining"
        assert item["credits_satisfied"] == pytest.approx(0.5)

    def test_ipr_course_can_fill_pending_slot_without_satisfying_required_slot(self):
        reqs = {
            "program_credits_required": 1.0,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "core",
                "label": "Core",
                "section": "core",
                "credits_required": 1.0,
                "items": [
                    {"id": "req", "type": "required", "courses": ["CSCA08H3"], "credits": 0.5, "label": "CS I"},
                    {"id": "list", "type": "n_credits_from_list", "credits_needed": 0.5, "courses": ["STAC32H3"], "label": "STA"},
                ],
            }],
        }
        acorn = {"terms": [{"term": "Winter 2024", "courses": [
            {"code": "STAC32H3", "grade": "IPR", "mark": None, "credits": 0.5},
        ]}]}
        result = check_graduation_progress(reqs, acorn)
        items = {item["id"]: item for item in result["groups"][0]["items"]}
        assert items["req"]["status"] == "remaining"
        assert items["list"]["status"] == "in_progress"

    def test_empty_acorn_history_returns_remaining(self):
        reqs = {
            "program_credits_required": 0.5,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "core", "label": "Core", "section": "core", "credits_required": 0.5,
                "items": [{"id": "req", "type": "required", "courses": ["CSCA08H3"], "credits": 0.5, "label": "CS I"}],
            }],
        }
        result = check_graduation_progress(reqs, {"terms": []})
        assert result["overall_status"] == "remaining"
        assert result["credits_satisfied"] == 0.0

    def test_coop_work_terms_are_checked(self):
        reqs = {
            "program_name": "Computer Science Specialist",
            "program_credits_required": 0.5,
            "degree_credits_required": 20.0,
            "is_coop": True,
            "groups": [{
                "id": "core", "label": "Core", "section": "core", "credits_required": 0.5,
                "items": [{"id": "req", "type": "required", "courses": ["CSCA08H3"], "credits": 0.5, "label": "CS I"}],
            }],
            "coop": {
                "work_terms_required": 2,
                "preparation": [],
                "search_courses": [],
                "work_term_courses": [
                    {"id": "wt1", "type": "required", "courses": ["COPB50H3"], "credits": 0.5, "label": "WT1"},
                    {"id": "wt2", "type": "required", "courses": ["COPB51H3"], "credits": 0.5, "label": "WT2"},
                ],
            },
        }
        acorn = {"terms": [{"term": "Fall 2023", "courses": [
            {"code": "CSCA08H3", "grade": "A", "mark": 85, "credits": 0.5},
            {"code": "COPB50H3", "grade": "A", "mark": 85, "credits": 0.5},
        ]}]}
        result = check_graduation_progress(reqs, acorn)
        assert result["coop"]["work_terms_completed"] == 1
        assert result["coop"]["work_terms_status"] == "in_progress"

    def test_reverse_only_exclusion_match_satisfies_requirement(self):
        reqs = {
            "program_credits_required": 0.5,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "core", "label": "Core", "section": "core", "credits_required": 0.5,
                "items": [{"id": "req", "type": "required", "courses": ["CSCA08H3"], "credits": 0.5, "label": "CS I"}],
            }],
        }
        acorn = {"terms": [{"term": "Fall 2023", "courses": [
            {"code": "CSC108H1", "grade": "A", "mark": 85, "credits": 0.5},
        ]}]}
        result = check_graduation_progress(reqs, acorn, exclusions_map={"CSCA08H3": {"CSC108H1"}})
        assert result["overall_status"] == "satisfied"

    def test_cross_campus_exclusion_lookup(self):
        """CSC108H1 (St. George) satisfies CSCA08H3 via the exclusions map."""
        reqs = {
            "program_credits_required": 0.5,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "cs1", "label": "Intro CS", "section": "core",
                "credits_required": 0.5,
                "items": [{
                    "id": "csca08", "type": "required",
                    "courses": ["CSCA08H3"], "credits": 0.5, "label": "Intro CS I",
                }],
            }],
        }
        acorn = {"terms": [{"term": "Fall 2023", "courses": [
            {"code": "CSC108H1", "grade": "A", "mark": 87, "credits": 0.5}
        ]}]}
        exclusions = {"CSC108H1": {"CSCA08H3"}}
        result = check_graduation_progress(reqs, acorn, exclusions_map=exclusions)
        assert result["overall_status"] == "satisfied"

    def test_no_double_counting(self):
        """A single course cannot satisfy two separate required items."""
        reqs = {
            "program_credits_required": 1.0,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "two_courses", "label": "Two Courses", "section": "core",
                "credits_required": 1.0,
                "items": [
                    {
                        "id": "item_a", "type": "required",
                        "courses": ["CSCA08H3"], "credits": 0.5, "label": "CS I",
                    },
                    {
                        "id": "item_b", "type": "required",
                        "courses": ["CSCA08H3"],  # same course
                        "credits": 0.5, "label": "CS I (duplicate)",
                    },
                ],
            }],
        }
        acorn = {"terms": [{"term": "Fall 2023", "courses": [
            {"code": "CSCA08H3", "grade": "A", "mark": 85, "credits": 0.5}
        ]}]}
        result = check_graduation_progress(reqs, acorn)
        # Only 0.5 credits satisfied (used once), not 1.0
        assert result["credits_satisfied"] == pytest.approx(0.5)
        assert result["overall_status"] == "remaining"

    def test_full_sample_fixture(self, sample_requirements, sample_acorn_data):
        """
        Using the shared fixtures:
        - CSCA08H3 (A) → satisfies csca08
        - CSCA48H3 (A+) → satisfies csca48
        - MATA30H3 (B+) → satisfies intro_calc
        - STAC32H3 (IPR) → in_progress for stats_list
        - No C-level CSC taken → csc_upper remaining

        Group needs 2.5 cr; satisfied=1.5, in_progress=0.5 → sat+ip=2.0 < 2.5
        → group status = "remaining" → overall status = "remaining"
        """
        result = check_graduation_progress(sample_requirements, sample_acorn_data)
        # Three items satisfied, one in_progress, one remaining
        items = {i["id"]: i for i in result["groups"][0]["items"]}
        assert items["csca08"]["status"] == "satisfied"
        assert items["csca48"]["status"] == "satisfied"
        assert items["intro_calc"]["status"] == "satisfied"
        assert items["stats_list"]["status"] == "in_progress"
        assert items["csc_upper"]["status"] == "remaining"
        # Group and overall are "remaining" because sat+ip (2.0) < required (2.5)
        assert result["overall_status"] == "remaining"
        assert result["credits_satisfied"] == pytest.approx(1.5)
        assert result["credits_in_progress"] == pytest.approx(0.5)


class TestGraduationDirectMatchers:
    def test_match_required_direct_and_exclusion_in_progress_and_remaining(self):
        item = {"id": "req", "type": "required", "courses": ["CSCA08H3"], "credits": 0.5, "label": "CS I"}
        result = _match_required(item, {"CSCA08H3": {"credits": 0.5}}, set(), set())
        assert result["status"] == "satisfied"

        result = _match_required(item, {}, {"CSC108H1"}, set(), {"CSC108H1": {"CSCA08H3"}})
        assert result["status"] == "in_progress"
        assert result["in_progress_via_exclusion"] == "CSCA08H3"

        result = _match_required(item, {}, set(), set(), {})
        assert result["status"] == "remaining"

    def test_match_n_credits_list_in_progress_and_exclusion(self):
        item = {"id": "list", "type": "n_credits_from_list", "credits_needed": 1.0, "courses": ["CSCA08H3", "CSCA48H3"], "label": "1.0 CSC"}
        result = _match_n_credits_list(item, {"CSC108H1": {"credits": 0.5}}, {"CSC148H1"}, set(), {"CSC108H1": {"CSCA08H3"}, "CSC148H1": {"CSCA48H3"}})
        assert result["credits_satisfied"] == pytest.approx(0.5)
        assert result["credits_in_progress"] == pytest.approx(0.5)
        assert result["status"] == "in_progress"

    def test_match_open_pool_in_progress_and_breaks_when_needed_reached(self):
        item = {
            "id": "pool",
            "type": "open_pool",
            "credits_needed": 0.5,
            "label": "0.5 CSC C-level",
            "filters": {"departments": ["CSC"], "levels": ["C"]},
            "exclusions": [],
            "sub_requirements": [],
        }
        result = _match_open_pool(item, {}, {"CSCC09H3", "CSCC10H3"}, set())
        assert result["status"] == "in_progress"
        assert result["credits_in_progress"] == pytest.approx(0.5)

    def test_match_open_pool_subrequirements_can_be_partially_in_progress(self):
        item = {
            "id": "pool",
            "type": "open_pool",
            "credits_needed": 1.0,
            "label": "Pool",
            "filters": {"departments": ["CSC", "STA"], "levels": ["C"]},
            "exclusions": [],
            "sub_requirements": [{
                "id": "sta",
                "label": "STA minimum",
                "departments": ["STA"],
                "levels": ["C"],
                "min_credits": 0.5,
            }],
        }
        result = _match_open_pool(item, {"CSCC09H3": {"credits": 0.5}}, {"STAC32H3"}, set())
        assert result["status"] == "in_progress"
        assert result["sub_requirements"][0]["status"] == "in_progress"

    def test_match_open_pool_breaks_when_subrequirement_or_pool_is_already_full(self):
        item = {
            "id": "pool",
            "type": "open_pool",
            "credits_needed": 0.5,
            "label": "Pool",
            "filters": {"departments": ["CSC", "STA"], "levels": ["C"]},
            "exclusions": [],
            "sub_requirements": [{
                "id": "sta",
                "label": "STA minimum",
                "departments": ["STA"],
                "levels": ["C"],
                "min_credits": 0.0,
            }],
        }
        result = _match_open_pool(item, {"CSCC09H3": {"credits": 0.5}, "STAC32H3": {"credits": 0.5}}, {"STAC33H3"}, set())
        assert result["credits_satisfied"] == pytest.approx(0.5)
        assert result["status"] == "satisfied"


class TestGraduationAdditionalProgress:
    def test_blank_codes_are_skipped_and_bad_mark_defaults_to_pass(self):
        reqs = {
            "program_credits_required": 0.5,
            "degree_credits_required": 20.0,
            "groups": [{
                "id": "core", "label": "Core", "section": "core", "credits_required": 0.5,
                "items": [{"id": "req", "type": "required", "courses": ["CSCA08H3"], "credits": 0.5, "label": "CS I"}],
            }],
        }
        acorn = {"terms": [{"courses": [
            {"code": "   ", "grade": "A", "mark": 90, "credits": 0.5},
            {"code": "CSCA08H3", "grade": "B", "mark": "not-a-number", "credits": 0.5},
        ]}]}
        result = check_graduation_progress(reqs, acorn)
        assert result["overall_status"] == "satisfied"
