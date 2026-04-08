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
            group_weight = self._resolve_group_weight(group, weights_lower)
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

    def build_weighted_components(
        self,
        assignment_groups: list[dict],
        submissions: list[dict],
        weights: dict[str, float],
    ) -> dict:
        """Build a conservative weighted component model for what-if sliders."""
        sub_by_id = {s["assignment_id"]: s for s in submissions}
        weights_lookup = {k.lower(): {"name": k, "weight": float(v)} for k, v in weights.items()}
        used_keys = set()
        components = []
        reliable = True

        for group in assignment_groups:
            group_model = self._build_group_components(group, sub_by_id, weights_lookup, used_keys)
            if group_model["components"]:
                components.extend(group_model["components"])
                used_keys.update(group_model["matched_keys"])
                if not group_model["reliable"]:
                    reliable = False
                continue

            group_key = self._match_weight_key(
                group["name"],
                {k: v["weight"] for k, v in weights_lookup.items()},
            )
            if group_key and group_key not in used_keys:
                group_components = self._build_group_weight_components(
                    group["name"],
                    group.get("assignments", []),
                    sub_by_id,
                    weights_lookup[group_key],
                )
                components.extend(group_components)
                used_keys.add(group_key)

        unmatched_weights = [
            data["name"]
            for key, data in weights_lookup.items()
            if key not in used_keys
        ]
        if unmatched_weights:
            for key, data in weights_lookup.items():
                if key in used_keys:
                    continue
                if not self._is_missing_future_component(data["name"]):
                    continue
                components.append({
                    "name": data["name"],
                    "weight": data["weight"],
                    "status": "ungraded",
                    "pct": None,
                    "earned": 0.0,
                    "possible": 0.0,
                    "source": "syllabus",
                    "group_name": None,
                })
                used_keys.add(key)

            unmatched_weights = [
                data["name"]
                for key, data in weights_lookup.items()
                if key not in used_keys
            ]
        if unmatched_weights:
            reliable = False

        return {
            "components": components,
            "total_weight": round(sum(c["weight"] for c in components), 2),
            "graded_weight": round(sum(c["weight"] for c in components if c["status"] == "graded"), 2),
            "ungraded_weight": round(sum(c["weight"] for c in components if c["status"] == "ungraded"), 2),
            "unmatched_weights": unmatched_weights,
            "reliable": reliable and bool(components),
        }

    def projected_grade(self, components: list[dict], slider_values: dict[str, float]) -> float:
        """Compute a projected final grade from graded components and sliders."""
        total = 0.0
        for component in components:
            if component["status"] == "graded":
                pct = component["pct"]
            elif component["status"] == "ungraded":
                pct = slider_values.get(component["name"], 100.0)
            else:
                raise ValueError(f"Cannot project partial component: {component['name']}")
            total += pct * component["weight"] / 100.0
        return round(total, 2)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_letter(pct: float) -> str:
        for letter, threshold in UOFT_THRESHOLDS:
            if pct >= threshold:
                return letter
        return "F"

    # Stop words excluded from fuzzy keyword matching
    _STOP_WORDS = {"the", "and", "to", "of", "a", "an", "in", "on", "for",
                   "with", "at", "by", "from", "or", "is", "its"}

    @classmethod
    def _keywords(cls, text: str) -> set[str]:
        """Extract meaningful root keywords from a string.

        Strips punctuation, splits on spaces and hyphens, lowercases, and
        removes stop words.  "Mid-term Examination" → {"mid", "term", "examination"}.
        """
        import re
        tokens = re.split(r"[\s\-_/]+", text.lower())
        tokens = [re.sub(r"[^a-z0-9]", "", t) for t in tokens]
        normalised = set()
        for token in tokens:
            if not token or token in cls._STOP_WORDS:
                continue
            normalised.add(token)
            # Light singularisation so "tests" can match "test".
            if len(token) > 3 and token.endswith("s"):
                normalised.add(token[:-1])
        return normalised

    @classmethod
    def _match_weight(cls, group_name: str, weights_lower: dict[str, float]) -> float | None:
        """Find a weight for a group by case-insensitive matching.

        Priority
        --------
        1. Exact match.
        2. Weight key is a substring of the group name.
        3. Group name is a substring of a weight key (prefer shortest key).
        4. Fuzzy keyword overlap — extract root keywords from both strings
           (split on spaces/hyphens, strip punctuation, drop stop words) and
           return the weight key with the most keyword tokens in common.
           Requires at least one meaningful keyword to overlap.
        """
        name_lower = group_name.lower()

        # 1. Exact
        if name_lower in weights_lower:
            return weights_lower[name_lower]

        # 2. Key contained in name
        for key, val in weights_lower.items():
            if key in name_lower:
                return val

        # 3. Name contained in key — prefer shortest key
        candidates = [(key, val) for key, val in weights_lower.items() if name_lower in key]
        if candidates:
            candidates.sort(key=lambda x: len(x[0]))
            return candidates[0][1]

        # 4. Fuzzy keyword overlap
        name_kw = cls._keywords(group_name)
        best_overlap, best_val = 0, None
        for key, val in weights_lower.items():
            overlap = len(name_kw & cls._keywords(key))
            if overlap > best_overlap:
                best_overlap, best_val = overlap, val
        if best_overlap > 0:
            return best_val

        return None

    @classmethod
    def _resolve_group_weight(cls, group: dict, weights_lower: dict[str, float]) -> float | None:
        """Resolve a Canvas group weight from either the group name or its items.

        Some courses use broad Canvas group names like "Assignments" or "Tests"
        while the syllabus lists item-level components such as
        "Personal Listening Questionnaire" and "Midterm Test". In that case,
        sum the distinct syllabus weights matched by assignment names inside the
        group.
        """
        direct = cls._match_weight(group["name"], weights_lower)
        if direct is not None:
            return direct

        matched_keys = set()
        total = 0.0
        for assignment in group.get("assignments", []):
            matched_key = cls._match_weight_key(assignment.get("name", ""), weights_lower)
            if matched_key is None or matched_key in matched_keys:
                continue
            matched_keys.add(matched_key)
            total += weights_lower[matched_key]

        return total if matched_keys else None

    @classmethod
    def _match_weight_key(cls, name: str, weights_lower: dict[str, float]) -> str | None:
        """Return the matched syllabus weight key rather than just its value."""
        name_lower = name.lower()

        if name_lower in weights_lower:
            return name_lower

        for key in weights_lower:
            if key in name_lower:
                return key

        candidates = [key for key in weights_lower if name_lower in key]
        if candidates:
            candidates.sort(key=len)
            return candidates[0]

        name_kw = cls._keywords(name)
        best_overlap, best_key = 0, None
        for key in weights_lower:
            overlap = len(name_kw & cls._keywords(key))
            if overlap > best_overlap:
                best_overlap, best_key = overlap, key
        if best_overlap > 0:
            return best_key

        return None

    @classmethod
    def _build_group_components(
        cls,
        group: dict,
        sub_by_id: dict[int, dict],
        weights_lookup: dict[str, dict],
        used_keys: set[str],
    ) -> dict:
        """Build the most specific reliable components available for one group.

        This supports mixed groups where one syllabus component maps to a
        specific assignment inside a broader Canvas group, and the remaining
        assignments should stay grouped under the broader syllabus category.
        """
        weights_only = {k: v["weight"] for k, v in weights_lookup.items()}
        group_key = cls._match_weight_key(group["name"], weights_only)
        components_by_key = {}
        matched_keys = set()
        unmatched_assignments = []
        scorable_seen = 0
        reliable = True

        for assignment in group.get("assignments", []):
            points_possible = assignment.get("points_possible") or 0
            if points_possible <= 0:
                continue
            scorable_seen += 1

            key = cls._best_assignment_weight_key(
                assignment.get("name", ""),
                group_key,
                weights_only,
                used_keys,
            )
            if key is None:
                unmatched_assignments.append(assignment)
                continue

            matched_keys.add(key)
            component = components_by_key.setdefault(key, {
                "name": weights_lookup[key]["name"],
                "weight": weights_lookup[key]["weight"],
                "status": "ungraded",
                "pct": None,
                "earned": 0.0,
                "possible": 0.0,
                "source": "assignment",
                "group_name": group["name"],
            })

            sub = sub_by_id.get(assignment["id"])
            if sub is not None and sub.get("score") is not None:
                component["earned"] += sub["score"]
                component["possible"] += points_possible

        if scorable_seen == 0:
            return {"components": [], "matched_keys": set(), "reliable": True}

        components = []
        for component in components_by_key.values():
            if component["possible"] > 0:
                component["pct"] = round((component["earned"] / component["possible"]) * 100, 2)
                component["status"] = "graded"
            components.append(component)

        if unmatched_assignments:
            if group_key and group_key not in used_keys and group_key not in matched_keys:
                residual_components = cls._build_group_weight_components(
                    group["name"],
                    unmatched_assignments,
                    sub_by_id,
                    weights_lookup[group_key],
                )
                components.extend(residual_components)
                matched_keys.add(group_key)
            elif matched_keys:
                reliable = False
            else:
                return {"components": [], "matched_keys": set(), "reliable": True}

        return {"components": components, "matched_keys": matched_keys, "reliable": reliable}

    @classmethod
    def _best_assignment_weight_key(
        cls,
        assignment_name: str,
        group_key: str | None,
        weights_lower: dict[str, float],
        unavailable_keys: set[str],
    ) -> str | None:
        """Prefer only specific item-level matches over the broad group match."""
        preferred = {
            key: value
            for key, value in weights_lower.items()
            if key not in unavailable_keys and key != group_key
        }
        return cls._match_weight_key(assignment_name, preferred)

    @classmethod
    def _is_missing_future_component(cls, name: str) -> bool:
        lower = name.lower()
        return "final" in lower or "exam" in lower

    @staticmethod
    def _build_group_weight_components(
        group_name: str,
        assignments: list[dict],
        sub_by_id: dict[int, dict],
        weight_info: dict,
    ) -> list[dict]:
        """Build group-level components, splitting completed vs remaining work.

        When only a coarse group weight is known, Canvas points provide the best
        available way to apportion that group's weight between already-graded and
        still-ungraded work.
        """
        earned = possible = 0.0
        total_possible = 0.0
        graded_count = 0
        ungraded_count = 0

        for assignment in assignments:
            points_possible = assignment.get("points_possible") or 0
            if points_possible <= 0:
                continue
            total_possible += points_possible
            sub = sub_by_id.get(assignment["id"])
            if sub is not None and sub.get("score") is not None:
                earned += sub["score"]
                possible += points_possible
                graded_count += 1
            else:
                ungraded_count += 1

        if total_possible == 0:
            return [{
                "name": weight_info["name"],
                "weight": weight_info["weight"],
                "status": "ungraded",
                "pct": None,
                "earned": 0.0,
                "possible": 0.0,
                "source": "group",
                "group_name": group_name,
            }]

        if not graded_count:
            return [{
                "name": weight_info["name"],
                "weight": weight_info["weight"],
                "status": "ungraded",
                "pct": None,
                "earned": 0.0,
                "possible": 0.0,
                "source": "group",
                "group_name": group_name,
            }]

        if not ungraded_count:
            return [{
                "name": weight_info["name"],
                "weight": weight_info["weight"],
                "status": "graded",
                "pct": round((earned / possible) * 100, 2) if possible > 0 else None,
                "earned": earned,
                "possible": possible,
                "source": "group",
                "group_name": group_name,
            }]

        graded_weight = weight_info["weight"] * (possible / total_possible)
        remaining_weight = weight_info["weight"] - graded_weight
        return [
            {
                "name": f"{weight_info['name']} (completed)",
                "weight": round(graded_weight, 2),
                "status": "graded",
                "pct": round((earned / possible) * 100, 2) if possible > 0 else None,
                "earned": earned,
                "possible": possible,
                "source": "group",
                "group_name": group_name,
            },
            {
                "name": f"{weight_info['name']} (remaining)",
                "weight": round(remaining_weight, 2),
                "status": "ungraded",
                "pct": None,
                "earned": 0.0,
                "possible": 0.0,
                "source": "group",
                "group_name": group_name,
            },
        ]
