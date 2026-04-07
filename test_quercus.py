"""
Test get_assignments() and get_submissions() for STAC51 and STAD68.

For each course prints:
  - Assignment: name, points_possible, due_at, and any weight-related fields
  - Submission: score, submitted_at, late status
"""

from integrations.quercus import QuercusClient, QuercusError

COURSES = {
    427986: "STAC51 — Categorical Data Analysis",
    428033: "STAD68 — Advanced Machine Learning and Data Mining",
}

# Fields that might carry grade-weight information
WEIGHT_FIELDS = (
    "group_weight",
    "assignment_group_id",
    "omit_from_final_grade",
    "grading_type",
    "submission_types",
)

client = QuercusClient()

for course_id, course_name in COURSES.items():
    print(f"\n{'='*70}")
    print(f"COURSE {course_id}: {course_name}")
    print(f"{'='*70}")

    try:
        assignments = client.get_assignments(course_id)
        submissions = client.get_submissions(course_id)
    except QuercusError as e:
        print(f"  ERROR: {e}")
        continue

    # Index submissions by assignment_id for quick lookup
    sub_by_assignment = {s["assignment_id"]: s for s in submissions}

    print(f"\n  {len(assignments)} assignments, {len(submissions)} submissions\n")

    for a in assignments:
        aid = a.get("id")
        print(f"  ASSIGNMENT  {aid}: {a.get('name')}")
        print(f"    points_possible : {a.get('points_possible')}")
        print(f"    due_at          : {a.get('due_at')}")
        print(f"    grading_type    : {a.get('grading_type')}")
        print(f"    omit_from_final : {a.get('omit_from_final_grade')}")
        print(f"    group_id        : {a.get('assignment_group_id')}")
        # Print any unexpected keys that look weight-related
        extra = {k: v for k, v in a.items()
                 if "weight" in k.lower() or "group" in k.lower()}
        if extra:
            print(f"    weight-related  : {extra}")

        sub = sub_by_assignment.get(aid)
        if sub:
            print(f"    SUBMISSION score      : {sub.get('score')} / {a.get('points_possible')}")
            print(f"    SUBMISSION grade      : {sub.get('grade')}")
            print(f"    SUBMISSION submitted  : {sub.get('submitted_at')}")
            print(f"    SUBMISSION late       : {sub.get('late')}")
            print(f"    SUBMISSION missing    : {sub.get('missing')}")
        else:
            print(f"    SUBMISSION: none")
        print()
