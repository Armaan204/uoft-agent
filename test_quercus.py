"""Test syllabus discovery and weight extraction for STAC51 and STAD68."""

import os
from dotenv import load_dotenv
from integrations.quercus import QuercusClient, QuercusError
from integrations.syllabus import parse_syllabus_weights, SyllabusError

load_dotenv()

COURSES = {
    428033: "STAD68 -- Advanced Machine Learning and Data Mining",
}

client = QuercusClient()

for course_id, course_name in COURSES.items():
    print(f"\n{'='*70}")
    print(f"COURSE {course_id}: {course_name}")
    print(f"{'='*70}")

    # Resolve syllabus_body PDF link (primary source)
    try:
        syllabus = client.get_syllabus(course_id)
        pdf_url = syllabus["pdf_urls"][0] if syllabus["pdf_urls"] else None
        print(f"  syllabus_body PDF     : {pdf_url or '(none)'}")
    except QuercusError as e:
        print(f"  ERROR fetching syllabus_body: {e}")
        pdf_url = None

    try:
        source_url, weights = parse_syllabus_weights(course_id, client, pdf_url)
        # Show which file was actually used
        filename = source_url.split("?")[0].rsplit("/", 1)[-1]
        print(f"  Source file           : {filename}")
        print(f"  Source URL            : {source_url[:80]}...")
        print(f"\n  Extracted weights:")
        for component, weight in weights.items():
            print(f"    {component:<40} {weight}%")
        total = sum(w for w in weights.values() if isinstance(w, (int, float)))
        print(f"    {'TOTAL':<40} {total}%")
    except SyllabusError as e:
        print(f"  ERROR: {e}")
