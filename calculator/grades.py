"""
calculator/grades.py — grade computation functions.

All methods are pure Python — no I/O, no LLM calls.  Input data comes
from the integrations layer (assignments, submissions, syllabus weights)
and is passed in as plain dicts/lists.
"""

# UofT letter-grade minimum thresholds, highest first
UOFT_THRESHOLDS = [
    ("A+", 90),
    ("A",  85),
    ("A-", 80),
    ("B+", 77),
    ("B",  73),
    ("B-", 70),
    ("C+", 67),
    ("C",  63),
    ("C-", 60),
    ("D+", 57),
    ("D",  53),
    ("F",   0),
]


class GradeCalculator:
    """Pure-math grade calculations for a single course."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def current_grade(
        self,
        assignment_groups: list[dict],
        submissions: list[dict],
        weights: dict[str, float],
    ) -> dict:
        """Compute the student's current weighted grade.

        Parameters
        ----------
        assignment_groups : list of group dicts from get_assignment_groups(),
            each containing 'name', 'id', and a nested 'assignments' list.
        submissions       : list of submission dicts from get_submissions(),
            each with 'assignment_id' and 'score'.
        weights           : dict mapping group name → percentage weight,
            as returned by parse_syllabus_weights().

        Returns
        -------
        dict with keys:
          weighted_grade   — overall grade as a percentage (graded work only)
          letter           — corresponding UofT letter grade
          group_breakdown  — per-group dict with earned, possible, pct, weight
          graded_weight    — sum of weights for groups that have graded work
        """
        sub_by_id = {s["assignment_id"]: s for s in submissions}

        # Normalise weight keys to lower-case for fuzzy matching
        weights_lower = {k.lower(): v for k, v in weights.items()}

        group_breakdown = {}

        for group in assignment_groups:
            group_name = group["name"]
            group_weight = self._match_weight(group_name, weights_lower)
            if group_weight is None:
                continue  # group not in syllabus weights — skip

            earned = 0.0
            possible = 0.0

            for assignment in group.get("assignments", []):
                sub = sub_by_id.get(assignment["id"])
                if sub is None or sub.get("score") is None:
                    continue  # not yet graded
                earned   += sub["score"]
                possible += assignment.get("points_possible") or 0

            if possible == 0:
                continue  # nothing graded in this group yet

            pct = (earned / possible) * 100
            group_breakdown[group_name] = {
                "earned":   earned,
                "possible": possible,
                "pct":      round(pct, 2),
                "weight":   group_weight,
            }

        # Weighted average over graded groups only; re-normalise weights
        graded_weight = sum(g["weight"] for g in group_breakdown.values())
        if graded_weight == 0:
            return {
                "weighted_grade":  0.0,
                "letter":          "N/A",
                "group_breakdown": {},
                "graded_weight":   0.0,
            }

        weighted_sum = sum(
            g["pct"] * (g["weight"] / graded_weight)
            for g in group_breakdown.values()
        )

        return {
            "weighted_grade":  round(weighted_sum, 2),
            "letter":          self._to_letter(weighted_sum),
            "group_breakdown": group_breakdown,
            "graded_weight":   graded_weight,
        }

    def needed_on_final(
        self,
        current_grade: float,
        final_weight: float,
        target_grade: float,
    ) -> dict:
        """Compute the score needed on a remaining assessment to hit a target.

        Solves:  current * (1 - w) + x * w = target
                 x = (target - current * (1 - w)) / w

        Parameters
        ----------
        current_grade : weighted grade on completed work, as a percentage.
        final_weight  : weight of the remaining assessment as a decimal
                        (e.g. 0.40 for a 40% final).
        target_grade  : desired overall course grade as a percentage.

        Returns
        -------
        dict with keys:
          needed   — required score as a percentage (float), or None
          status   — "needed" | "already_achieved" | "impossible"
          message  — human-readable string
        """
        non_final_weight = 1.0 - final_weight

        # Grade already locked in from completed work
        locked = current_grade * non_final_weight

        if locked >= target_grade:
            return {
                "needed":  None,
                "status":  "already_achieved",
                "message": (
                    f"Already on track for {target_grade:.0f}% — "
                    f"current completed work contributes {locked:.1f}% "
                    f"toward the final grade."
                ),
            }

        needed = (target_grade - locked) / final_weight

        if needed > 100:
            return {
                "needed":  round(needed, 1),
                "status":  "impossible",
                "message": (
                    f"Would need {needed:.1f}% on the remaining {final_weight*100:.0f}% "
                    f"assessment — not achievable."
                ),
            }

        return {
            "needed":  round(needed, 1),
            "status":  "needed",
            "message": (
                f"Need {needed:.1f}% on the remaining "
                f"{final_weight*100:.0f}% assessment to reach {target_grade:.0f}%."
            ),
        }

    def grade_scenarios(
        self,
        current_grade: float,
        final_weight: float,
    ) -> dict[str, dict]:
        """Return what final score is needed to achieve each UofT letter grade.

        Parameters
        ----------
        current_grade : weighted grade on completed work, as a percentage.
        final_weight  : weight of the remaining assessment as a decimal.

        Returns
        -------
        dict mapping letter grade → needed_on_final() result dict.
        """
        return {
            letter: self.needed_on_final(current_grade, final_weight, threshold)
            for letter, threshold in UOFT_THRESHOLDS
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_letter(pct: float) -> str:
        for letter, threshold in UOFT_THRESHOLDS:
            if pct >= threshold:
                return letter
        return "F"

    @staticmethod
    def _match_weight(group_name: str, weights_lower: dict[str, float]) -> float | None:
        """Find a weight for a group by case-insensitive matching.

        Priority
        --------
        1. Exact match.
        2. Weight key is a substring of the group name (key is specific).
        3. Group name is a substring of a weight key (less specific — among
           multiple candidates pick the shortest key to avoid "Final Project"
           matching "Final Project Proposal" instead of "Final Project").
        """
        name_lower = group_name.lower()

        # 1. Exact
        if name_lower in weights_lower:
            return weights_lower[name_lower]

        # 2. Key contained in name
        for key, val in weights_lower.items():
            if key in name_lower:
                return val

        # 3. Name contained in key — prefer shortest key (closest match)
        candidates = [(key, val) for key, val in weights_lower.items() if name_lower in key]
        if candidates:
            candidates.sort(key=lambda x: len(x[0]))
            return candidates[0][1]

        return None
