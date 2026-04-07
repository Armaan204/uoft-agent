"""Test current_grade and grade_scenarios for EESA10 (420065)."""

from dotenv import load_dotenv
from integrations.quercus import QuercusClient
from calculator.grades import GradeCalculator

load_dotenv()

COURSE_ID = 420065
client = QuercusClient()
calc   = GradeCalculator()

# --- Weights (Canvas-native, no syllabus parsing needed) ---
weights = client.get_canvas_weights(COURSE_ID)
print(f"Weights source: Canvas group_weight")
for name, w in weights.items():
    print(f"  {name:<20} {w}%")

# --- Current grade ---
groups      = client.get_assignment_groups(COURSE_ID)
submissions = client.get_submissions(COURSE_ID)
result      = calc.current_grade(groups, submissions, weights)

print(f"\nCurrent grade breakdown:")
for group, g in result["group_breakdown"].items():
    print(f"  {group:<20} {g['earned']:.1f}/{g['possible']:.1f} = {g['pct']:.1f}%  (weight: {g['weight']}%)")
print(f"\n  Graded weight : {result['graded_weight']}%")
print(f"  Weighted grade: {result['weighted_grade']}%  ({result['letter']})")

# --- Grade scenarios (Final Exam = 40%) ---
FINAL_WEIGHT = 0.40
print(f"\nGrade scenarios (Final Exam = {FINAL_WEIGHT*100:.0f}%):")
scenarios = calc.grade_scenarios(result["weighted_grade"], FINAL_WEIGHT)
for letter, r in scenarios.items():
    if r["status"] == "already_achieved":
        print(f"  {letter:<3} already achieved")
    elif r["status"] == "impossible":
        print(f"  {letter:<3} impossible (would need {r['needed']}%)")
    else:
        print(f"  {letter:<3} need {r['needed']}% on final")
