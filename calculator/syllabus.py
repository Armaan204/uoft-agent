"""
calculator/syllabus.py — syllabus parsing for grade weights.

When a course does not expose assessment weights through the Quercus
API, this module attempts to extract them from the syllabus text.

Planned functions
-----------------
- extract_weights_from_html(html)
    Parse Canvas syllabus HTML and return a dict mapping assessment
    name → percentage weight (e.g. {"Midterm": 30, "Final": 40, ...}).
    Uses heuristics to find grade-breakdown tables or bullet lists.

- extract_weights_from_pdf(pdf_bytes)
    Parse a raw PDF syllabus (common for uploaded course outlines) and
    return the same dict format.  Falls back to regex patterns when
    table detection fails.

- normalise_weights(raw_weights)
    Validate and normalise a raw weight dict: ensure values are numeric,
    warn if they do not sum to 100, and return a cleaned copy.
"""
