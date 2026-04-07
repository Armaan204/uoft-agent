"""
Test the full syllabus discovery + weight extraction pipeline on
STAC51 (427986), MUZA99 (425621), and EESA10 (420065).
Shows which fallback fired and the extracted weights for each course.
"""

from dotenv import load_dotenv
from integrations.quercus import QuercusClient, QuercusError
from integrations.syllabus import (
    find_syllabus_file,
    find_syllabus_frontpage,
    parse_syllabus_weights,
    SyllabusError,
)

load_dotenv()

COURSES = {
    427986: "STAC51 -- Categorical Data Analysis",
    425621: "MUZA99 -- Listening to Music",
    420065: "EESA10 -- Human Health and the Environment",
}

client = QuercusClient()

for course_id, course_name in COURSES.items():
    print(f"\n{'='*68}")
    print(f"COURSE {course_id}: {course_name}")
    print(f"{'='*68}")

    # Show which fallback finds something
    syllabus = client.get_syllabus(course_id)
    pdf_url  = syllabus["pdf_urls"][0] if syllabus["pdf_urls"] else None

    if pdf_url:
        print(f"  Source: syllabus_body PDF link")
    else:
        fb2 = find_syllabus_file(course_id, client)
        if fb2:
            print(f"  Source: files/modules search")
            pdf_url = fb2
        else:
            fb3 = find_syllabus_frontpage(course_id, client)
            if fb3:
                print(f"  Source: front page link")
                pdf_url = fb3
            else:
                print(f"  Source: none found")

    if not pdf_url:
        print("  Weights: N/A")
        continue

    print(f"  URL   : {pdf_url[:72]}...")
    try:
        _src, weights = parse_syllabus_weights(course_id, client, pdf_url)
        print(f"  Weights:")
        for component, weight in weights.items():
            print(f"    {component:<40} {weight}%")
        total = sum(w for w in weights.values() if isinstance(w, (int, float)))
        print(f"    {'TOTAL':<40} {total}%")
    except SyllabusError as e:
        print(f"  ERROR: {e}")
