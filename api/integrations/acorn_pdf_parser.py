"""
api/integrations/acorn_pdf_parser.py — Deterministic regex-based parser for
ACORN "Complete Academic History" PDFs.

Produces the same JSON shape as the Chrome extension so downstream code
(acorn_store.validate_payload, acorn_service, frontend) works unchanged.
"""

from __future__ import annotations

import io
import re
from datetime import datetime, timezone

from pypdf import PdfReader


class AcornPdfParseError(Exception):
    """Raised when an ACORN PDF cannot be parsed."""


# ---------------------------------------------------------------------------
# Course-code patterns
# ---------------------------------------------------------------------------
_REGULAR_CODE_RE = re.compile(
    r"^(?:[A-Z]{4}\d{2}|[A-Z]{3}\d{3})[A-Z]\d$"
)
_TRANSFER_CODE_RE = re.compile(r"^[A-Z]{4}\*{3}$")

# ---------------------------------------------------------------------------
# Token classifiers
# ---------------------------------------------------------------------------
_CREDIT_RE = re.compile(r"^\d+\.\d{2}$")
_MARK_RE = re.compile(r"^\d{1,3}$")
_GRADE_TOKENS = frozenset(
    {
        "A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-",
        "D+", "D", "D-", "F",
        "CR", "NCR", "NGA", "IPR", "LWD", "GWR", "SDF", "WD", "P", "FL%", "NC%",
    }
)
_TRANSFER_GRADE_RE = re.compile(r"^[A-Z]\d{2}$")

# ---------------------------------------------------------------------------
# Structural-line patterns (applied per-line, not multiline)
# ---------------------------------------------------------------------------
_TERM_HEADING_RE = re.compile(
    r"^(\d{4}\s+(?:Fall|Winter|Summer))\s+-\s+(.+)"
)
_SESSIONAL_GPA_RE = re.compile(r"Sessional\s+GPA\s+([\d.]+)", re.IGNORECASE)
_CUMULATIVE_GPA_RE = re.compile(r"Cumulative\s+GPA\s+([\d.]+)", re.IGNORECASE)
_STATUS_RE = re.compile(r"^Status:\s*(.+)", re.IGNORECASE)
_TABLE_HEADER_RE = re.compile(r"Crs\s+Code\s+Title", re.IGNORECASE)
_CREDITS_EARNED_RE = re.compile(r"Credits\s+Earned:\s*([\d.]+)", re.IGNORECASE)
_DEANS_LIST_RE = re.compile(r"Dean.?s\s+List", re.IGNORECASE)

# Program / enrollment patterns
_ENROLLMENT_PERIOD_RE = re.compile(
    r"^(\d{4}\s+(?:Fall|Winter|Summer))\s*-\s*(\d{4}\s+(?:Fall|Winter|Summer))\s*:\s*(.+)$",
    re.IGNORECASE,
)
_STATUS_LINE_RE = re.compile(
    r"^(Completed|In\s+Progress|Graduated|Suspended|Withdrawn|Transferred|Inactive)\s*-\s*(.+)$",
    re.IGNORECASE,
)
_SESSION_PREFIX_RE = re.compile(
    r"^(\d{4}\s+(?:Fall|Winter|Summer))\s*-\s*(.+)$",
    re.IGNORECASE,
)


# ===================================================================
# Public API
# ===================================================================

def parse_acorn_pdf(pdf_bytes: bytes) -> dict:
    """Parse an ACORN Complete Academic History PDF into the canonical
    import payload shape (identical to what the Chrome extension produces)."""
    text = _extract_text(pdf_bytes)
    if not text.strip():
        raise AcornPdfParseError("PDF contains no extractable text")

    normalized = text.lower().replace("\n", " ")
    if "registration history" not in normalized and "complete academic history" not in normalized:
        raise AcornPdfParseError("This does not appear to be an ACORN Complete Academic History PDF")

    lines = text.split("\n")

    # ---- locate term headings ----
    term_indices: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        m = _TERM_HEADING_RE.match(stripped)
        if m and not _DEANS_LIST_RE.search(stripped):
            term_indices.append((i, m.group(1).strip()))

    # ---- preamble: everything before the first term heading ----
    preamble_end = term_indices[0][0] if term_indices else len(lines)
    preamble_lines = lines[:preamble_end]

    programs = _parse_programs(preamble_lines)
    transfer_courses = _parse_course_table(preamble_lines, term_name=None)

    # ---- parse each term block ----
    terms: list[dict] = []
    for idx, (start, term_name) in enumerate(term_indices):
        end = term_indices[idx + 1][0] if idx + 1 < len(term_indices) else len(lines)
        block_lines = lines[start:end]
        terms.append(_parse_term_block(block_lines, term_name))

    all_courses = [c for t in terms for c in t["courses"]] + transfer_courses
    if not all_courses and not terms:
        raise AcornPdfParseError("No courses or terms found in the PDF")

    return {
        "terms": terms,
        "courses": all_courses,
        "programs": programs,
        "importedAt": datetime.now(timezone.utc).isoformat(),
        "source": "pdf",
    }


# ===================================================================
# Text extraction
# ===================================================================

def _extract_text(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        raise AcornPdfParseError("Could not read PDF") from exc
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


# ===================================================================
# Term block parsing
# ===================================================================

def _parse_term_block(block_lines: list[str], term_name: str) -> dict:
    block_text = "\n".join(block_lines)

    sess = _SESSIONAL_GPA_RE.search(block_text)
    cum = _CUMULATIVE_GPA_RE.search(block_text)

    status = None
    for line in block_lines:
        m = _STATUS_RE.match(line.strip())
        if m:
            status = m.group(1).strip()
            break

    courses = _parse_course_table(block_lines, term_name)

    return {
        "term": term_name,
        "sessionalGpa": float(sess.group(1)) if sess else None,
        "cumulativeGpa": float(cum.group(1)) if cum else None,
        "status": status,
        "courses": courses,
    }


# ===================================================================
# Course table parsing (line-by-line)
# ===================================================================

def _is_course_code(token: str) -> bool:
    return bool(_REGULAR_CODE_RE.match(token) or _TRANSFER_CODE_RE.match(token))


def _is_grade_token(token: str) -> bool:
    return token.upper() in _GRADE_TOKENS


def _parse_course_table(block_lines: list[str], term_name: str | None) -> list[dict]:
    """Extract courses from lines, handling multi-line titles."""
    courses: list[dict] = []
    current: dict | None = None

    for line in block_lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Skip structural lines
        if (
            _TABLE_HEADER_RE.search(stripped)
            or _CREDITS_EARNED_RE.search(stripped)
            or _TERM_HEADING_RE.match(stripped)
            or _SESSIONAL_GPA_RE.search(stripped)
            or _STATUS_RE.match(stripped)
            or _DEANS_LIST_RE.search(stripped)
            or stripped.startswith("Registration History")
            or stripped.lower().startswith("this is not an official")
            or stripped.lower().startswith("complete academic")
            or _ENROLLMENT_PERIOD_RE.match(stripped)
            or _STATUS_LINE_RE.match(stripped)
        ):
            continue

        tokens = stripped.split()
        first = tokens[0] if tokens else ""

        if _is_course_code(first):
            if current is not None:
                courses.append(current)
            current = _parse_first_course_line(tokens, term_name)
        elif current is not None:
            _handle_continuation(current, tokens)

    if current is not None:
        courses.append(current)

    for c in courses:
        c.pop("_is_transfer", None)

    return courses


def _parse_first_course_line(tokens: list[str], term_name: str | None) -> dict:
    """Parse the first (main) line of a course entry."""
    course_code = tokens[0]
    is_transfer = "***" in course_code

    # Find credit token
    credit_index = None
    for i, tok in enumerate(tokens[1:], 1):
        if _CREDIT_RE.match(tok):
            credit_index = i
            break

    if credit_index is None or credit_index <= 1:
        return {
            "courseCode": course_code,
            "title": " ".join(tokens[1:]),
            "credits": None,
            "mark": None,
            "grade": None,
            "courseAverage": None,
            "rawText": None,
            "term": term_name,
        }

    credits = tokens[credit_index]
    title = " ".join(tokens[1:credit_index])

    # Parse trailing tokens for mark / grade / courseAverage
    trailing = tokens[credit_index + 1:]
    mark: str | None = None
    grade: str | None = None
    course_average: str | None = None

    for tok in trailing:
        if mark is None and _MARK_RE.match(tok):
            val = int(tok)
            if 0 <= val <= 100:
                mark = tok
                continue

        if grade is None and _is_grade_token(tok):
            grade = tok.upper()
            continue

        if grade is not None and course_average is None and _is_grade_token(tok):
            course_average = tok.upper()
            continue

        if grade is None and _TRANSFER_GRADE_RE.match(tok):
            grade = tok.upper()

    # COP-prefix correction
    if course_code.startswith("COP"):
        credits = "0.00"
        mark = None
    elif grade and grade == "CR" and credits == "0.00":
        credits = "0.50"

    return {
        "courseCode": course_code,
        "title": title,
        "credits": credits,
        "mark": mark,
        "grade": grade,
        "courseAverage": course_average,
        "rawText": None,
        "term": term_name,
        "_is_transfer": is_transfer,
    }


def _handle_continuation(current: dict, tokens: list[str]) -> None:
    """Process a continuation line (indented, no course code at start)."""
    is_transfer = current.get("_is_transfer", False)

    if is_transfer:
        for tok in tokens:
            if current.get("grade") is None and _TRANSFER_GRADE_RE.match(tok):
                current["grade"] = tok.upper()
    else:
        current["title"] = (current.get("title") or "") + " " + " ".join(tokens)


# ===================================================================
# Program parsing
# ===================================================================

def _is_structural_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    tokens = stripped.split()
    first = tokens[0] if tokens else ""
    return bool(
        _TERM_HEADING_RE.match(stripped)
        or _ENROLLMENT_PERIOD_RE.match(stripped)
        or _DEANS_LIST_RE.search(stripped)
        or _TABLE_HEADER_RE.search(stripped)
        or _CREDITS_EARNED_RE.search(stripped)
        or _is_course_code(first)
    )


def _parse_programs(preamble_lines: list[str]) -> list[dict]:
    programs: list[dict] = []

    enrollment_period: str | None = None
    institution: str | None = None

    i = 0
    while i < len(preamble_lines):
        line = preamble_lines[i].strip()
        if not line:
            i += 1
            continue

        ep = _ENROLLMENT_PERIOD_RE.match(line)
        if ep:
            enrollment_period = f"{ep.group(1).strip()}-{ep.group(2).strip()}"
            institution = ep.group(3).strip()
            i += 1
            continue

        if enrollment_period:
            sm = _STATUS_LINE_RE.match(line)
            if sm:
                enrollment_status = re.sub(r"\s+", " ", sm.group(1)).strip()
                rest = sm.group(2).strip()

                # Gather continuation lines for multi-line program names
                j = i + 1
                while j < len(preamble_lines):
                    next_line = preamble_lines[j].strip()
                    if not next_line:
                        j += 1
                        continue
                    if _is_structural_line(preamble_lines[j]):
                        break
                    if _STATUS_LINE_RE.match(next_line):
                        break
                    rest += " " + next_line
                    j += 1
                i = j

                start_session: str | None = None
                program_name: str | None
                sp = _SESSION_PREFIX_RE.match(rest)
                if sp:
                    start_session = sp.group(1).strip()
                    program_name = sp.group(2).strip()
                else:
                    program_name = rest

                programs.append(
                    {
                        "enrollmentPeriod": enrollment_period,
                        "institution": institution,
                        "enrollmentStatus": enrollment_status,
                        "startSession": start_session,
                        "programName": program_name,
                    }
                )
                continue

        i += 1

    return programs
