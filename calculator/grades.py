"""
calculator/grades.py — grade computation functions.

Implements the core calculations that power the agent's grade-related
answers.  All functions are pure (no I/O, no global state) and operate
on plain dicts / lists so they are easy to unit-test.

Planned functions
-----------------
- weighted_average(scores, weights)
    Compute the weighted mean of a set of assessment scores given their
    percentage weights.  Weights need not sum to 100 — missing weight is
    treated as ungraded.

- required_score(current_weighted, remaining_weight, target_grade)
    Return the minimum score needed on the remaining assessment(s) to
    reach target_grade overall.  Returns None if the target is already
    achieved or mathematically impossible.

- letter_to_gpa(letter_grade)
    Convert a UofT letter grade (e.g. "A-") to the 4.0 GPA scale value.

- gpa_average(course_records)
    Compute the cumulative GPA from a list of (grade, credit) pairs
    using UofT's weighted-GPA formula.
"""
