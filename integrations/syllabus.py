"""
integrations/syllabus.py — syllabus PDF discovery and weight extraction.

Two public entry points:

  find_syllabus_file(course_id, client)
      Searches a course's file list for the most likely syllabus document
      when the syllabus_body HTML contains no PDF link.

  parse_syllabus_weights(course_id, client, pdf_url=None)
      Downloads a syllabus PDF, extracts text, and asks Claude Haiku to
      return a JSON grade-weight breakdown.  Falls back to
      find_syllabus_file() when pdf_url is not provided.
"""

import io
import json
import os

import anthropic
import requests
from dotenv import load_dotenv
from pypdf import PdfReader

load_dotenv()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SYLLABUS_KEYWORDS = ["syllabus", "outline", "course info", "course guide", "schedule"]
_ALLOWED_EXTENSIONS = {".pdf", ".docx"}


class SyllabusError(Exception):
    """Raised when a syllabus cannot be found, downloaded, or parsed."""


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def _score_filename(name: str) -> int:
    """Return the number of syllabus-related keywords found in a filename."""
    lower = name.lower()
    return sum(1 for kw in _SYLLABUS_KEYWORDS if kw in lower)


def find_syllabus_file(course_id: int | str, client) -> str | None:
    """Search a course's file list for the most likely syllabus document.

    Fetches all files via GET /courses/{id}/files, filters to .pdf and .docx,
    scores each filename against syllabus-related keywords, and returns the
    pre-signed download URL of the best match.  Returns None if no file scores
    above zero.

    Parameters
    ----------
    course_id : Canvas course ID.
    client    : An authenticated QuercusClient instance.
    """
    try:
        files = client.get_course_files(course_id)
    except Exception:
        # Canvas returns 403 on courses where file listing is restricted.
        # Treat as "no files found" so the caller can try other strategies.
        return None

    candidates = []
    for f in files:
        name = f.get("display_name") or f.get("filename") or ""
        ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in _ALLOWED_EXTENSIONS:
            continue
        score = _score_filename(name)
        if score > 0:
            candidates.append((score, name, f.get("url")))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    _score, best_name, best_url = candidates[0]
    return best_url


# ---------------------------------------------------------------------------
# Weight extraction
# ---------------------------------------------------------------------------

def _download_pdf(url: str) -> bytes:
    """Download a file from a pre-signed URL and return raw bytes."""
    response = requests.get(url, allow_redirects=True, timeout=30)
    if not response.ok:
        raise SyllabusError(
            f"Failed to download syllabus ({response.status_code}): {url}"
        )
    return response.content


def _extract_text(pdf_bytes: bytes) -> str:
    """Extract plain text from a PDF byte string using pypdf."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as exc:
        raise SyllabusError(f"pypdf could not read PDF: {exc}") from exc
    if not text:
        raise SyllabusError("PDF contained no extractable text")
    return text


def _ask_claude(text: str) -> dict:
    """Send syllabus text to Claude Haiku and return a parsed weight dict."""
    claude = anthropic.Anthropic()

    prompt = (
        "Below is text extracted from a university course syllabus.\n"
        "Identify every graded component and its percentage weight.\n"
        "Return ONLY a valid JSON object mapping each component name to its "
        "weight as a number, for example:\n"
        '{"Assignments": 40, "Midterm": 25, "Final Exam": 35}\n'
        "If a component lists multiple sub-items, use the parent category name "
        "and its total weight. Do not include any explanation or markdown.\n\n"
        f"SYLLABUS TEXT:\n{text[:12000]}"
    )

    message = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        weights = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SyllabusError(f"Claude returned non-JSON response: {raw!r}") from exc

    if not isinstance(weights, dict):
        raise SyllabusError(f"Expected a JSON object, got: {type(weights)}")

    return weights


def parse_syllabus_weights(
    course_id: int | str,
    client,
    pdf_url: str = None,
) -> tuple[str, dict[str, float]]:
    """Extract grade weights from a course syllabus PDF.

    Resolution order
    ----------------
    1. Use pdf_url directly if provided (from syllabus_body HTML links).
    2. Fall back to find_syllabus_file() to search the course file list.

    Parameters
    ----------
    course_id : Canvas course ID (used only for the fallback search).
    client    : An authenticated QuercusClient instance.
    pdf_url   : Pre-resolved download URL, or None to trigger the fallback.

    Returns
    -------
    (source_url, weights) — the URL that was actually parsed, and a dict
    mapping assessment component name to percentage weight.

    Raises
    ------
    SyllabusError if no PDF can be found or the weights cannot be parsed.
    """
    source_url = pdf_url

    if not source_url:
        source_url = find_syllabus_file(course_id, client)

    if not source_url:
        raise SyllabusError(
            f"No syllabus PDF found for course {course_id} "
            "(no syllabus_body links and no matching files)"
        )

    pdf_bytes = _download_pdf(source_url)
    text = _extract_text(pdf_bytes)
    weights = _ask_claude(text)

    return source_url, weights
