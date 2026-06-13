"""
tests/test_calculator.py — unit tests for calculator/grades.py.

All tests are pure Python: no mocking, no I/O.
"""

import pytest
from unittest.mock import patch
from api.calculator.grades import GradeCalculator, UOFT_THRESHOLDS, UOFT_GPA_POINTS

calc = GradeCalculator()


# ── letter grade boundaries ───────────────────────────────────────────────────

class TestLetterGrade:
    @pytest.mark.parametrize("pct,expected", [
        (90, "A+"),
        (89, "A"),
        (85, "A"),
        (84, "A-"),
        (80, "A-"),
        (79, "B+"),
        (77, "B+"),
        (76, "B"),
        (73, "B"),
        (72, "B-"),
        (70, "B-"),
        (69, "C+"),
        (67, "C+"),
        (66, "C"),
        (63, "C"),
        (62, "C-"),
        (60, "C-"),
        (59, "D+"),
        (57, "D+"),
        (56, "D"),
        (53, "D"),
        (49, "F"),
        (0,  "F"),
    ])
    def test_letter_grade_thresholds(self, pct, expected):
        assert calc._to_letter(pct) == expected

    def test_a_plus_and_a_both_map_to_4_0_gpa(self):
        assert UOFT_GPA_POINTS["A+"] == 4.0
        assert UOFT_GPA_POINTS["A"] == 4.0

    def test_f_maps_to_0_gpa(self):
        assert UOFT_GPA_POINTS["F"] == 0.0

    def test_negative_percentage_still_maps_to_f(self):
        assert calc._to_letter(-1.0) == "F"


# ── weighted average calculation ──────────────────────────────────────────────

class TestCurrentGrade:
    def test_basic_weighted_average(self, sample_assignment_groups, sample_submissions, sample_weights):
        """
        Midterm (40%) = 78%, Assignments (20%) = (45+40)/(50+50) = 85%.
        Final (40%) has no submission, so graded_weight = 60%.
        Re-normalised: midterm weight 40/60, assignments weight 20/60.
        Expected = (78 * 40/60) + (85 * 20/60) ≈ 80.33.
        """
        result = calc.current_grade(
            sample_assignment_groups, sample_submissions, sample_weights
        )
        assert result["weighted_grade"] == pytest.approx(80.33, abs=0.1)
        assert result["letter"] == "A-"

    def test_no_graded_assignments_returns_zero(self):
        groups = [{"id": 1, "name": "Assignments", "rules": {}, "assignments": [
            {"id": 10, "name": "A1", "points_possible": 100}
        ]}]
        result = calc.current_grade(groups, [], {"Assignments": 100.0})
        assert result["weighted_grade"] == 0.0
        assert result["letter"] == "N/A"
        assert result["graded_weight"] == 0.0

    def test_unknown_group_name_skipped(self):
        """Groups not in the syllabus weights dict are ignored."""
        groups = [
            {"id": 1, "name": "Participation", "rules": {}, "assignments": [
                {"id": 10, "name": "Attendance", "points_possible": 10}
            ]}
        ]
        subs = [{"assignment_id": 10, "score": 10.0}]
        weights = {"Midterm": 100.0}   # no "Participation" key
        result = calc.current_grade(groups, subs, weights)
        assert result["weighted_grade"] == 0.0   # no groups matched

    def test_perfect_score_returns_a_plus(self):
        groups = [{"id": 1, "name": "Total", "rules": {}, "assignments": [
            {"id": 10, "name": "Final", "points_possible": 100}
        ]}]
        subs = [{"assignment_id": 10, "score": 100.0}]
        result = calc.current_grade(groups, subs, {"Total": 100.0})
        assert result["weighted_grade"] == 100.0
        assert result["letter"] == "A+"

    def test_full_weights_sum_to_100_when_all_graded(
        self, sample_assignment_groups, sample_submissions, sample_weights
    ):
        # Add a submission for the Final so all groups are graded
        all_subs = sample_submissions + [{"assignment_id": 201, "score": 70.0}]
        result = calc.current_grade(sample_assignment_groups, all_subs, sample_weights)
        # graded_weight should equal sum of all weights (100%)
        assert result["graded_weight"] == pytest.approx(100.0, abs=0.1)

    def test_group_breakdown_keys_match_group_names(
        self, sample_assignment_groups, sample_submissions, sample_weights
    ):
        result = calc.current_grade(sample_assignment_groups, sample_submissions, sample_weights)
        # Midterm and Assignments have graded work; Final does not
        breakdown = result["group_breakdown"]
        assert "Midterm" in breakdown
        assert "Assignments" in breakdown
        assert "Final" not in breakdown   # no submission → excluded


# ── needed_on_final math ──────────────────────────────────────────────────────

class TestNeededOnFinal:
    def test_standard_needed_score(self):
        """current=78%, final_weight=0.4, target=80% → need (80 - 78*0.6) / 0.4 = 83%."""
        result = calc.needed_on_final(78.0, 0.4, 80.0)
        assert result["status"] == "needed"
        assert result["needed"] == pytest.approx(83.0, abs=0.2)

    def test_already_achieved(self):
        """When the locked-in portion already covers the target."""
        # current=95, non-final weight=0.6 → locked = 57 > 55 (target)
        result = calc.needed_on_final(95.0, 0.4, 55.0)
        assert result["status"] == "already_achieved"
        assert result["needed"] is None

    def test_impossible(self):
        """When even 100% on the final won't reach the target."""
        # current=50, final_weight=0.4, target=90 → need (90-30)/0.4 = 150%
        result = calc.needed_on_final(50.0, 0.4, 90.0)
        assert result["status"] == "impossible"
        assert result["needed"] > 100

    def test_exactly_on_boundary(self):
        """Score at the exact boundary should trigger 'already_achieved'."""
        # locked = 80 * 0.6 = 48 == target 48
        result = calc.needed_on_final(80.0, 0.4, 48.0)
        assert result["status"] == "already_achieved"

    def test_zero_final_weight_already_achieved(self):
        result = calc.needed_on_final(82.0, 0.0, 80.0)
        assert result["status"] == "already_achieved"
        assert result["needed"] is None

    def test_zero_final_weight_impossible(self):
        result = calc.needed_on_final(82.0, 0.0, 90.0)
        assert result["status"] == "impossible"
        assert result["needed"] is None


# ── grade scenarios ───────────────────────────────────────────────────────────

class TestGradeScenarios:
    def test_returns_all_letter_grades(self):
        scenarios = calc.grade_scenarios(75.0, 0.4)
        expected_letters = {lt for lt, _ in UOFT_THRESHOLDS}
        assert set(scenarios.keys()) == expected_letters

    def test_easy_grades_already_achieved(self):
        """
        With current=100 and 40% remaining:
          locked = 100 * 0.6 = 60
        Grades with threshold ≤ 60 should already be achieved: F(0), D(53), D+(57), C-(60).
        """
        scenarios = calc.grade_scenarios(100.0, 0.4)
        # thresholds at or below 60 → already locked in
        easy = ["F", "D", "D+", "C-"]
        for letter in easy:
            assert scenarios[letter]["status"] == "already_achieved", (
                f"Expected {letter} to be already_achieved, got {scenarios[letter]['status']}"
            )

    def test_impossible_grade_when_failing(self):
        """With current=20 and 40% remaining, A+ should be impossible."""
        scenarios = calc.grade_scenarios(20.0, 0.4)
        assert scenarios["A+"]["status"] == "impossible"

    def test_monotonic_needed_scores(self):
        """Higher letter grades require higher scores on the final."""
        scenarios = calc.grade_scenarios(70.0, 0.4)
        needed = {
            lt: scenarios[lt]["needed"]
            for lt in ["B-", "B", "B+", "A-", "A"]
            if scenarios[lt]["status"] == "needed"
        }
        scores = list(needed.values())
        assert scores == sorted(scores), "needed scores should be monotonically increasing"

    def test_all_grades_already_achieved_when_no_remaining_weight(self):
        scenarios = calc.grade_scenarios(100.0, 0.0)
        assert all(result["status"] == "already_achieved" for result in scenarios.values())


# ── drop rule logic ───────────────────────────────────────────────────────────

class TestDropRules:
    def test_drop_lowest_excludes_worst_quiz(
        self, drop_rule_groups, drop_rule_submissions
    ):
        """Quiz 1 (40%) should be dropped; remaining: Quiz 2 (70%), Quiz 3 (100%) → 85%."""
        result = calc.current_grade(
            drop_rule_groups, drop_rule_submissions, {"Quizzes": 30.0}
        )
        # Midterm/Final not present; only Quizzes (graded_weight=30)
        # Remaining quizzes: 7+10=17 out of 20 = 85%
        assert result["weighted_grade"] == pytest.approx(85.0, abs=0.1)
        assert len(result["dropped_assignment_ids"]) == 1
        assert 501 in result["dropped_assignment_ids"]

    def test_drop_highest_excludes_best(self):
        """drop_highest=1 drops Quiz 3 (100%); remaining: 40% + 70% = 55%."""
        groups = [
            {
                "id": 50, "name": "Quizzes", "group_weight": 30.0,
                "rules": {"drop_highest": 1},
                "assignments": [
                    {"id": 501, "name": "Q1", "points_possible": 10},
                    {"id": 502, "name": "Q2", "points_possible": 10},
                    {"id": 503, "name": "Q3", "points_possible": 10},
                ],
            }
        ]
        subs = [
            {"assignment_id": 501, "score": 4.0},
            {"assignment_id": 502, "score": 7.0},
            {"assignment_id": 503, "score": 10.0},
        ]
        result = calc.current_grade(groups, subs, {"Quizzes": 30.0})
        assert 503 in result["dropped_assignment_ids"]
        assert result["weighted_grade"] == pytest.approx(55.0, abs=0.1)

    def test_never_drop_protects_assignment(self):
        """never_drop=[502] should prevent Quiz 2 from being dropped as lowest."""
        groups = [
            {
                "id": 50, "name": "Quizzes", "group_weight": 30.0,
                "rules": {"drop_lowest": 1, "never_drop": [502]},
                "assignments": [
                    {"id": 501, "name": "Q1", "points_possible": 10},
                    {"id": 502, "name": "Q2", "points_possible": 10},
                    {"id": 503, "name": "Q3", "points_possible": 10},
                ],
            }
        ]
        subs = [
            {"assignment_id": 501, "score": 4.0},
            {"assignment_id": 502, "score": 3.0},  # would be lowest, but protected
            {"assignment_id": 503, "score": 10.0},
        ]
        result = calc.current_grade(groups, subs, {"Quizzes": 30.0})
        # Q2 is protected; Q1 (next lowest) is dropped
        assert 501 in result["dropped_assignment_ids"]
        assert 502 not in result["dropped_assignment_ids"]

    def test_no_rules_drops_nothing(self, sample_assignment_groups, sample_submissions, sample_weights):
        """Groups with empty rules dict drop nothing."""
        result = calc.current_grade(sample_assignment_groups, sample_submissions, sample_weights)
        assert result["dropped_assignment_ids"] == []


# ── projected_grade ───────────────────────────────────────────────────────────

class TestProjectedGrade:
    def test_all_graded_no_slider(self):
        components = [
            {"component_key": "mid", "name": "Midterm", "weight": 50.0, "status": "graded", "pct": 80.0},
            {"component_key": "fin", "name": "Final",   "weight": 50.0, "status": "graded", "pct": 90.0},
        ]
        assert calc.projected_grade(components, {}) == pytest.approx(85.0)

    def test_slider_overrides_ungraded_component(self):
        components = [
            {"component_key": "mid", "name": "Midterm", "weight": 60.0, "status": "graded", "pct": 70.0},
            {"component_key": "fin", "name": "Final",   "weight": 40.0, "status": "ungraded", "pct": None},
        ]
        # slider sets Final to 100%
        result = calc.projected_grade(components, {"fin": 100.0})
        assert result == pytest.approx(0.6 * 70.0 + 0.4 * 100.0)

    def test_ungraded_defaults_to_100_when_no_slider(self):
        """Ungraded component with no slider defaults to 100% contribution."""
        components = [
            {"component_key": "fin", "name": "Final", "weight": 100.0, "status": "ungraded", "pct": None},
        ]
        result = calc.projected_grade(components, {})
        assert result == pytest.approx(100.0)

    def test_empty_components_returns_zero(self):
        assert calc.projected_grade([], {}) == 0.0

    def test_slider_accepts_zero_percent_and_hundred_percent(self):
        components = [
            {"component_key": "mid", "name": "Midterm", "weight": 50.0, "status": "graded", "pct": 80.0},
            {"component_key": "fin", "name": "Final", "weight": 50.0, "status": "ungraded", "pct": None},
        ]
        assert calc.projected_grade(components, {"fin": 0.0}) == pytest.approx(40.0)
        assert calc.projected_grade(components, {"fin": 100.0}) == pytest.approx(90.0)


# ── build_weighted_components ─────────────────────────────────────────────────

class TestBuildWeightedComponents:
    def test_basic_component_model_built(self):
        groups = [{"id": 10, "name": "Midterm", "group_weight": 40.0, "rules": {}, "assignments": [
            {"id": 101, "name": "Midterm Exam", "points_possible": 100}
        ]}]
        submissions = [{"assignment_id": 101, "score": 78.0}]
        weights = {"Midterm": 40.0}
        model = calc.build_weighted_components(groups, submissions, weights)
        assert "components" in model
        assert isinstance(model["components"], list)
        assert "reliable" in model

    def test_empty_groups_yields_empty_model(self):
        model = calc.build_weighted_components([], [], {})
        assert model["components"] == []
        assert model["reliable"] is False

    def test_unmatched_weight_becomes_ungraded_component(self):
        """A syllabus weight with no matching Canvas group becomes an ungraded component."""
        groups = [{"id": 10, "name": "Assignments", "group_weight": 50.0, "rules": {}, "assignments": [
            {"id": 101, "name": "HW1", "points_possible": 10}
        ]}]
        submissions = []
        # "FinalExam" weight has no matching group → added as ungraded component
        weights = {"Assignments": 50.0, "FinalExam": 50.0}
        model = calc.build_weighted_components(groups, submissions, weights)
        # _is_missing_future_component always returns True, so it gets added ungraded
        ungraded_names = [c["name"] for c in model["components"] if c["status"] == "ungraded"]
        assert "FinalExam" in ungraded_names

    def test_mixed_graded_and_ungraded_assignments_in_same_group_split_components(self):
        groups = [{
            "id": 10,
            "name": "Assignments",
            "group_weight": 100.0,
            "rules": {},
            "assignments": [
                {"id": 101, "name": "A1", "points_possible": 40},
                {"id": 102, "name": "A2", "points_possible": 60},
            ],
        }]
        submissions = [{"assignment_id": 101, "score": 32.0}]
        model = calc.build_weighted_components(groups, submissions, {"Assignments": 100.0})
        statuses = {component["status"] for component in model["components"]}
        assert statuses == {"graded", "ungraded"}
        assert model["graded_weight"] == pytest.approx(40.0)
        assert model["ungraded_weight"] == pytest.approx(60.0)

    def test_unmatched_non_future_weight_marks_model_unreliable(self):
        with patch.object(GradeCalculator, "_is_missing_future_component", return_value=False):
            model = calc.build_weighted_components(
                [{"id": 1, "name": "Assignments", "rules": {}, "assignments": []}],
                [],
                {"Ghost Final": 100.0},
            )
        assert model["reliable"] is False
        assert model["unmatched_weights"] == ["Ghost Final"]

    def test_group_model_unreliable_propagates_to_overall_model(self):
        with patch.object(GradeCalculator, "_build_group_components", return_value={"components": [{"name": "X", "weight": 100.0, "status": "ungraded"}], "matched_keys": set(), "reliable": False, "assignments_by_component": {}}):
            model = calc.build_weighted_components([{"id": 1, "name": "Assignments", "assignments": []}], [], {})
        assert model["reliable"] is False

    def test_build_weighted_components_falls_back_to_group_weight_builder_when_group_model_empty(self):
        with patch.object(GradeCalculator, "_build_group_components", return_value={"components": [], "matched_keys": set(), "reliable": True, "assignments_by_component": {}}), \
             patch.object(GradeCalculator, "_build_group_weight_components", return_value={"components": [{"component_key": "x", "name": "Assignments", "weight": 100.0, "status": "ungraded", "pct": None, "earned": 0.0, "possible": 0.0, "source": "group", "group_name": "Assignments"}], "assignments_by_component": {"x": []}}) as mock_builder:
            model = calc.build_weighted_components(
                [{"id": 1, "name": "Assignments", "assignments": [{"id": 10, "points_possible": 100}], "rules": {}}],
                [],
                {"Assignments": 100.0},
            )
        mock_builder.assert_called_once()
        assert model["components"][0]["name"] == "Assignments"


class TestInternalComponentBuilders:
    def test_build_group_components_returns_empty_when_only_non_scorable(self):
        result = calc._build_group_components(
            {"id": 1, "name": "Assignments", "assignments": [{"id": 10, "name": "A1", "points_possible": 0}]},
            {},
            {"assignments": {"name": "Assignments", "weight": 100.0}},
            set(),
            set(),
        )
        assert result["components"] == []
        assert result["reliable"] is True

    def test_build_group_components_falls_back_to_group_component_for_unmatched_assignment(self):
        result = calc._build_group_components(
            {
                "id": 1,
                "name": "Assignments",
                "assignments": [
                    {"id": 10, "name": "Essay 1", "points_possible": 100},
                    {"id": 11, "name": "Project", "points_possible": 100},
                ],
            },
            {10: {"assignment_id": 10, "score": 80.0}},
            {
                "essay 1": {"name": "Essay 1", "weight": 30.0},
                "assignments": {"name": "Assignments", "weight": 70.0},
            },
            set(),
            set(),
        )
        names = {component["name"] for component in result["components"]}
        assert "Essay 1" in names
        assert "Assignments" in names
        assert result["reliable"] is True

    def test_build_group_components_marks_reliable_false_when_unmatched_after_specific_match(self):
        result = calc._build_group_components(
            {
                "id": 1,
                "name": "Assignments",
                "assignments": [
                    {"id": 10, "name": "Essay 1", "points_possible": 100},
                    {"id": 11, "name": "Mystery", "points_possible": 100},
                ],
            },
            {10: {"assignment_id": 10, "score": 80.0}},
            {"essay 1": {"name": "Essay 1", "weight": 100.0}},
            set(),
            set(),
        )
        assert result["reliable"] is False
        assert result["components"][0]["name"] == "Essay 1"

    def test_build_group_components_returns_empty_when_nothing_matches(self):
        result = calc._build_group_components(
            {"id": 1, "name": "Assignments", "assignments": [{"id": 10, "name": "Mystery", "points_possible": 100}]},
            {},
            {"exam": {"name": "Exam", "weight": 100.0}},
            set(),
            set(),
        )
        assert result == {"components": [], "matched_keys": set(), "reliable": True, "assignments_by_component": {}}

    def test_build_group_weight_components_all_nonscorable_returns_ungraded_all(self):
        result = calc._build_group_weight_components(
            1,
            "Assignments",
            [{"id": 10, "name": "A1", "points_possible": 0}],
            {},
            {"name": "Assignments", "weight": 100.0},
            set(),
        )
        assert result["components"][0]["status"] == "ungraded"
        assert result["components"][0]["component_key"].endswith("::all")

    def test_build_group_weight_components_all_ungraded_returns_pending_component(self):
        result = calc._build_group_weight_components(
            1,
            "Assignments",
            [{"id": 10, "name": "A1", "points_possible": 100}],
            {},
            {"name": "Assignments", "weight": 100.0},
            set(),
        )
        assert result["components"][0]["component_key"].endswith("::pending")
        assert result["assignments_by_component"]

    def test_build_group_weight_components_all_graded_returns_graded_component(self):
        result = calc._build_group_weight_components(
            1,
            "Assignments",
            [{"id": 10, "name": "A1", "points_possible": 100}],
            {10: {"assignment_id": 10, "score": 0.0}},
            {"name": "Assignments", "weight": 100.0},
            set(),
        )
        assert result["components"][0]["status"] == "graded"
        assert result["components"][0]["pct"] == 0.0

    def test_null_score_is_ungraded_but_zero_score_is_graded(self):
        result = calc._build_group_weight_components(
            1,
            "Assignments",
            [
                {"id": 10, "name": "Null score", "points_possible": 50},
                {"id": 11, "name": "Zero score", "points_possible": 50},
            ],
            {
                10: {"assignment_id": 10, "score": None},
                11: {"assignment_id": 11, "score": 0.0},
            },
            {"name": "Assignments", "weight": 100.0},
            set(),
        )
        statuses = {row["name"]: row["status"] for rows in result["assignments_by_component"].values() for row in rows}
        assert statuses["Null score"] == "ungraded"
        assert statuses["Zero score"] == "graded"

    def test_build_group_weight_components_skips_dropped_assignments(self):
        result = calc._build_group_weight_components(
            1,
            "Assignments",
            [{"id": 10, "name": "Dropped", "points_possible": 100}],
            {10: {"assignment_id": 10, "score": 100.0}},
            {"name": "Assignments", "weight": 100.0},
            {10},
        )
        assert result["components"][0]["component_key"].endswith("::all")


class TestDroppedAssignmentHelpersExtended:
    def test_resolve_dropped_assignment_ids_skips_zero_possible_assignments(self):
        group = {
            "rules": {"drop_lowest": 1},
            "assignments": [
                {"id": 1, "points_possible": 0},
                {"id": 2, "points_possible": 10},
            ],
        }
        sub_by_id = {1: {"score": 0.0}, 2: {"score": 5.0}}
        assert calc._resolve_dropped_assignment_ids(group, sub_by_id) == {2}


# ── _match_weight ─────────────────────────────────────────────────────────────

class TestMatchWeight:
    def test_exact_match(self):
        assert calc._match_weight("Midterm", {"midterm": 40.0}) == 40.0

    def test_key_contained_in_name(self):
        # "quiz" contained in "quiz section"
        assert calc._match_weight("Quiz Section", {"quiz": 20.0}) == 20.0

    def test_name_contained_in_key(self):
        # group name "final" contained in key "final exam"
        result = calc._match_weight("final", {"final exam": 50.0})
        assert result == 50.0

    def test_fuzzy_keyword_overlap(self):
        # "quiz weekly" and "weekly quiz" share keywords "quiz" and "weekly"
        # but neither is a substring of the other → resolved via keyword overlap
        result = calc._match_weight("quiz weekly", {"weekly quiz": 20.0})
        assert result == 20.0

    def test_no_match_returns_none(self):
        result = calc._match_weight("Completely Unrelated", {"something_else": 30.0})
        assert result is None


# ── current_grade additional branches ────────────────────────────────────────

class TestCurrentGradeAdditional:
    def test_group_with_zero_points_possible_skipped(self):
        """A group where all assignments have points_possible=0 is skipped."""
        groups = [{"id": 1, "name": "Bonus", "rules": {}, "assignments": [
            {"id": 10, "name": "Bonus Points", "points_possible": 0}
        ]}]
        submissions = [{"assignment_id": 10, "score": 5.0}]
        result = calc.current_grade(groups, submissions, {"Bonus": 10.0})
        # No graded weight → zero grade
        assert result["weighted_grade"] == 0.0

    def test_drop_fewer_assignments_than_count(self):
        """drop_lowest=5 with only 2 assignments — all get dropped, nothing to grade."""
        groups = [{"id": 1, "name": "Quizzes", "group_weight": 30.0,
                   "rules": {"drop_lowest": 5},
                   "assignments": [
                       {"id": 1, "name": "Q1", "points_possible": 10},
                       {"id": 2, "name": "Q2", "points_possible": 10},
                   ]}]
        submissions = [
            {"assignment_id": 1, "score": 8.0},
            {"assignment_id": 2, "score": 9.0},
        ]
        result = calc.current_grade(groups, submissions, {"Quizzes": 30.0})
        # All assignments dropped → no graded work
        assert result["weighted_grade"] == 0.0

    def test_gpa_points_present_in_result(self):
        """Result dict includes gpa_points mapping."""
        groups = [{"id": 1, "name": "Assignments", "rules": {}, "assignments": [
            {"id": 10, "name": "A1", "points_possible": 100}
        ]}]
        subs = [{"assignment_id": 10, "score": 90.0}]
        result = calc.current_grade(groups, subs, {"Assignments": 100.0})
        assert result["gpa_points"] == 4.0  # 90% → A+ → 4.0

    def test_to_gpa_points_all_grades(self):
        """_to_gpa_points should return a float for every valid letter."""
        for letter, _ in UOFT_THRESHOLDS:
            threshold = _
            gpa = calc._to_gpa_points(threshold)
            assert isinstance(gpa, float)

    def test_zero_score_counts_but_null_score_does_not(self):
        groups = [{
            "id": 1,
            "name": "Assignments",
            "rules": {},
            "assignments": [
                {"id": 10, "name": "A1", "points_possible": 100},
                {"id": 11, "name": "A2", "points_possible": 100},
            ],
        }]
        submissions = [
            {"assignment_id": 10, "score": 0.0},
            {"assignment_id": 11, "score": None},
        ]
        result = calc.current_grade(groups, submissions, {"Assignments": 100.0})
        assert result["group_breakdown"]["Assignments"]["earned"] == 0.0
        assert result["group_breakdown"]["Assignments"]["possible"] == 100.0
        assert result["weighted_grade"] == 0.0

    def test_cr_ncr_style_assignment_without_points_possible_is_skipped(self):
        groups = [{
            "id": 1,
            "name": "Participation",
            "rules": {},
            "assignments": [{"id": 10, "name": "CR/NCR item", "points_possible": None}],
        }]
        submissions = [{"assignment_id": 10, "score": 1.0}]
        result = calc.current_grade(groups, submissions, {"Participation": 100.0})
        assert result["graded_weight"] == 0.0
        assert result["letter"] == "N/A"


class TestProjectedGradeAdditional:
    def test_partial_component_raises_value_error(self):
        with pytest.raises(ValueError, match="Cannot project partial component"):
            calc.projected_grade([
                {"component_key": "mid", "name": "Midterm", "weight": 100.0, "status": "partial", "pct": 50.0}
            ], {})


class TestMatchingAndHelpers:
    def test_keywords_remove_stop_words_and_singularize(self):
        result = calc._keywords("The weekly tests in class")
        assert "the" not in result
        assert "weekly" in result
        assert "tests" in result
        assert "test" in result

    def test_resolve_group_weight_sums_distinct_item_weights(self):
        group = {
            "name": "Assignments",
            "assignments": [
                {"name": "Essay 1"},
                {"name": "Essay 1 duplicate"},
                {"name": "Essay 2"},
            ],
        }
        weights_lower = {"essay 1": 15.0, "essay 2": 20.0}
        assert calc._resolve_group_weight(group, weights_lower) == 35.0

    def test_match_weight_key_prefers_shortest_container_and_fuzzy_match(self):
        assert calc._match_weight_key("final", {"final exam": 50.0, "final project showcase": 50.0}) == "final exam"
        assert calc._match_weight_key("weekly quiz", {"quiz weekly": 10.0}) == "quiz weekly"

    def test_normalize_component_weights_scales_to_hundred(self):
        components = [
            {"name": "A", "weight": 33.0},
            {"name": "B", "weight": 33.0},
            {"name": "C", "weight": 33.0},
        ]
        normalized = calc._normalize_component_weights(components)
        assert round(sum(component["weight"] for component in normalized), 2) == 100.0


class TestBuildGroupWeightComponents:
    def test_total_possible_zero_returns_single_ungraded_component(self):
        result = calc._build_group_weight_components(
            1,
            "Final",
            [{"id": 10, "name": "Final", "points_possible": 0}],
            {},
            {"name": "Final", "weight": 40.0},
            set(),
        )
        assert result["components"][0]["status"] == "ungraded"
        assert result["components"][0]["component_key"].endswith("::all")

    def test_all_ungraded_returns_pending_component(self):
        result = calc._build_group_weight_components(
            2,
            "Assignments",
            [{"id": 11, "name": "A1", "points_possible": 10}],
            {},
            {"name": "Assignments", "weight": 20.0},
            set(),
        )
        assert result["components"][0]["component_key"].endswith("::pending")
        assert result["assignments_by_component"]

    def test_all_graded_returns_graded_component(self):
        result = calc._build_group_weight_components(
            3,
            "Midterm",
            [{"id": 12, "name": "Midterm", "points_possible": 100}],
            {12: {"score": 80.0}},
            {"name": "Midterm", "weight": 30.0},
            set(),
        )
        assert result["components"][0]["status"] == "graded"
        assert result["components"][0]["pct"] == 80.0


class TestDroppedAssignmentHelpers:
    def test_resolve_dropped_assignment_ids_returns_empty_when_no_graded_candidates(self):
        group = {
            "rules": {"drop_lowest": 1},
            "assignments": [{"id": 1, "points_possible": 10}],
        }
        assert calc._resolve_dropped_assignment_ids(group, {}) == set()


class TestGroupKeyExclusionRegression:
    """Regression: numbered items in a collective group must each match their
    own weight key, not get cross-matched when the group name fuzzy-matches
    one of the item keys and excludes it from candidates."""

    def _numbered_group(self):
        return [{
            "id": 100,
            "name": "Quizzes",
            "group_weight": 25.0,
            "rules": {},
            "assignments": [
                {"id": 1, "name": "Test A", "points_possible": 50},
                {"id": 2, "name": "Test B", "points_possible": 50},
            ],
        }]

    def _numbered_weights(self):
        return {"Test A": 12.5, "Test B": 12.5, "Midterm": 30.0, "Final": 45.0}

    def test_first_item_graded_maps_to_correct_component(self):
        submissions = [{"assignment_id": 1, "score": 50.0}]
        model = calc.build_weighted_components(
            self._numbered_group(), submissions, self._numbered_weights(),
        )
        by_name = {c["name"]: c for c in model["components"]}
        assert by_name["Test A"]["status"] == "graded"
        assert by_name["Test A"]["pct"] == 100.0
        assert by_name["Test B"]["status"] == "ungraded"

    def test_second_item_graded_maps_to_correct_component(self):
        submissions = [{"assignment_id": 2, "score": 40.0}]
        model = calc.build_weighted_components(
            self._numbered_group(), submissions, self._numbered_weights(),
        )
        by_name = {c["name"]: c for c in model["components"]}
        assert by_name["Test B"]["status"] == "graded"
        assert by_name["Test B"]["pct"] == 80.0
        assert by_name["Test A"]["status"] == "ungraded"

    def test_both_items_graded_maps_independently(self):
        submissions = [
            {"assignment_id": 1, "score": 50.0},
            {"assignment_id": 2, "score": 25.0},
        ]
        model = calc.build_weighted_components(
            self._numbered_group(), submissions, self._numbered_weights(),
        )
        by_name = {c["name"]: c for c in model["components"]}
        assert by_name["Test A"]["pct"] == 100.0
        assert by_name["Test B"]["pct"] == 50.0

    def test_multiple_numbered_items_in_collective_group(self):
        groups = [{
            "id": 200,
            "name": "Labs",
            "group_weight": 30.0,
            "rules": {},
            "assignments": [
                {"id": 10, "name": "Lab 1", "points_possible": 20},
                {"id": 11, "name": "Lab 2", "points_possible": 20},
                {"id": 12, "name": "Lab 3", "points_possible": 20},
            ],
        }]
        submissions = [{"assignment_id": 11, "score": 18.0}]
        weights = {"Lab 1": 10.0, "Lab 2": 10.0, "Lab 3": 10.0, "Final": 70.0}
        model = calc.build_weighted_components(groups, submissions, weights)
        by_name = {c["name"]: c for c in model["components"]}
        assert by_name["Lab 2"]["status"] == "graded"
        assert by_name["Lab 2"]["pct"] == 90.0
        assert by_name["Lab 1"]["status"] == "ungraded"
        assert by_name["Lab 3"]["status"] == "ungraded"


class TestCrossGroupFuzzyMismatchRegression:
    """Regression: an assignment whose name shares a keyword with a *different*
    group's weight key must fall back to its own group weight, not cross-match
    via fuzzy overlap.

    The trigger requires the assignment name to share one keyword with its own
    group key and a *different* keyword with another group's key — both overlaps
    equal 1, so the group fallback must win."""

    def test_shared_keyword_does_not_cross_match(self):
        """'Research Summary' in group 'Research Paper' must not fuzzy-match
        to 'Course Summary' via 'summary' — the group keyword 'research'
        has equal overlap so the group fallback should win."""
        groups = [
            {
                "id": 1,
                "name": "Research Paper",
                "group_weight": 15.0,
                "rules": {},
                "assignments": [
                    {"id": 101, "name": "Research Summary", "points_possible": 100},
                ],
            },
            {
                "id": 2,
                "name": "Course Summary",
                "group_weight": 20.0,
                "rules": {},
                "assignments": [
                    {"id": 201, "name": "Course Summary 1", "points_possible": 10},
                    {"id": 202, "name": "Course Summary 2", "points_possible": 10},
                ],
            },
        ]
        submissions = [
            {"assignment_id": 101, "score": 87.0},
            {"assignment_id": 201, "score": 10.0},
        ]
        weights = {
            "Research Paper": 15.0,
            "Course Summary": 20.0,
            "Final Exam": 65.0,
        }
        model = calc.build_weighted_components(groups, submissions, weights)
        by_name = {c["name"]: c for c in model["components"]}
        assert by_name["Research Paper"]["status"] == "graded"
        assert by_name["Research Paper"]["pct"] == 87.0
        assert by_name["Course Summary"]["status"] == "graded"
        assert by_name["Course Summary"]["pct"] == 100.0
