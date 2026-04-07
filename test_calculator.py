"""
Test GradeCalculator with real STAD68 data.

Pulls live assignments, submissions, and syllabus weights, then runs
current_grade(), needed_on_final(), and grade_scenarios().
"""

from dotenv import load_dotenv
from integrations.quercus import QuercusClient
from integrations.syllabus import parse_syllabus_weights
from calculator.grades import GradeCalculator

load_dotenv()

COURSE_ID = 428033

client = QuercusClient()
calc   = GradeCalculator()

print("Fetching STAD68 data from Quercus...")
assignment_groups = client.get_assignment_groups(COURSE_ID)
submissions       = client.get_submissions(COURSE_ID)

print("Extracting syllabus weights...")
syllabus  = client.get_syllabus(COURSE_ID)
pdf_url   = syllabus["pdf_urls"][0] if syllabus["pdf_urls"] else None
_src, weights = parse_syllabus_weights(COURSE_ID, client, pdf_url)

print(f"Weights: {weights}\n")

# -----------------------------------------------------------------------
# 1. Current grade
# -----------------------------------------------------------------------
result = calc.current_grade(assignment_groups, submissions, weights)

print("=" * 60)
print("CURRENT GRADE")
print("=" * 60)
for group, g in result["group_breakdown"].items():
    print(f"  {group:<30} {g['earned']:.1f}/{g['possible']:.1f} "
          f"= {g['pct']:.1f}%  (weight: {g['weight']}%)")
print(f"\n  Graded weight so far : {result['graded_weight']}%")
print(f"  Weighted grade       : {result['weighted_grade']}%")
print(f"  Letter grade         : {result['letter']}")

# -----------------------------------------------------------------------
# 2. Needed on final
# -----------------------------------------------------------------------
# STAD68 has no traditional "final exam" — use the Final Project (40%)
# as the "remaining" assessment since it hasn't been graded yet.
FINAL_WEIGHT  = 0.40
TARGET_GRADES = [90, 85, 80, 70]

print("\n" + "=" * 60)
print(f"NEEDED ON FINAL PROJECT ({FINAL_WEIGHT*100:.0f}% weight)")
print("=" * 60)
for target in TARGET_GRADES:
    r = calc.needed_on_final(result["weighted_grade"], FINAL_WEIGHT, target)
    print(f"  Target {target}%  ->  {r['message']}")

# -----------------------------------------------------------------------
# 3. Grade scenarios
# -----------------------------------------------------------------------
print("\n" + "=" * 60)
print(f"GRADE SCENARIOS  (Final Project = {FINAL_WEIGHT*100:.0f}%)")
print("=" * 60)
scenarios = calc.grade_scenarios(result["weighted_grade"], FINAL_WEIGHT)
for letter, r in scenarios.items():
    if r["status"] == "already_achieved":
        print(f"  {letter:<3}  already achieved")
    elif r["status"] == "impossible":
        print(f"  {letter:<3}  impossible (would need {r['needed']}%)")
    else:
        print(f"  {letter:<3}  need {r['needed']}% on final project")
