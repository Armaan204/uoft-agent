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
import re

import anthropic
import requests
import streamlit as st
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pypdf import PdfReader

from integrations.syllabus_cache import (
    SyllabusCacheError,
    get_cached_syllabus_weights,
    save_cached_syllabus_weights,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SYLLABUS_KEYWORDS = ["syllabus", "outline", "course info", "course guide", "schedule"]
_ALLOWED_EXTENSIONS = {".pdf", ".docx"}
_CONFIDENCE_THRESHOLD = 0.3   # score / len(_SYLLABUS_KEYWORDS) must exceed this
_LLM_PICK_CANDIDATE_LIMIT = 10
_DIRECT_PICK_MIN_CONFIDENCE = 0.15


class SyllabusError(Exception):
    """Raised when a syllabus cannot be found, downloaded, or parsed."""


def _get_anthropic_client() -> anthropic.Anthropic:
    """Build an Anthropic client from the runtime environment.

    The Streamlit app resolves secrets on the main thread during startup and
    mirrors ANTHROPIC_API_KEY into os.environ. Syllabus parsing may run in a
    worker thread, so this module avoids reading st.secrets at import time.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise SyllabusError("ANTHROPIC_API_KEY is not configured")
    return anthropic.Anthropic(api_key=api_key)


# ---------------------------------------------------------------------------
# File discovery helpers
# ---------------------------------------------------------------------------

def _confidence(name: str) -> float:
    """Keyword-match confidence in [0, 1] for a filename."""
    lower = name.lower()
    hits = sum(1 for kw in _SYLLABUS_KEYWORDS if kw in lower)
    return hits / len(_SYLLABUS_KEYWORDS)


def _score_candidate(*texts: str) -> float:
    """Return the best syllabus confidence across multiple text signals."""
    scores = [_confidence(text) for text in texts if text]
    return max(scores) if scores else 0.0


def _allowed_ext(name: str) -> bool:
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext in _ALLOWED_EXTENSIONS


def _extract_page_slug(href: str) -> str | None:
    """Extract a Canvas wiki page slug from a course page URL."""
    match = re.search(r"/pages/([^/?#]+)", href)
    if not match:
        return None
    return match.group(1)


def _collect_file_candidates(course_id: int | str, client) -> list[dict]:
    """Return all .pdf/.docx files from the course files API.

    Each entry has keys: name, url, confidence.
    Returns [] silently on 403 (restricted course).
    """
    try:
        files = client.get_course_files(course_id)
    except Exception:
        return []

    candidates = []
    for f in files:
        name = f.get("display_name") or f.get("filename") or ""
        if not _allowed_ext(name):
            continue
        candidates.append({
            "name":       name,
            "filename":   name,
            "label":      name,
            "url":        f.get("url"),
            "confidence": _score_candidate(name),
        })
    return candidates


def _collect_file_candidates_debug(course_id: int | str, client) -> tuple[list[dict], str | None]:
    """Debug wrapper for course files discovery."""
    try:
        return _collect_file_candidates(course_id, client), None
    except Exception as exc:
        return [], str(exc)


def _collect_module_candidates(course_id: int | str, client) -> list[dict]:
    """Return .pdf/.docx file items found inside course modules.

    Walks every module's items, picks File-type items, resolves the file ID
    to a download URL, and scores the item title.
    Returns [] silently on error.
    """
    try:
        modules = client.get_course_modules(course_id)
    except Exception:
        return []

    seen_ids = set()
    candidates = []
    for module in modules:
        for item in module.get("items", []):
            if item.get("type") != "File":
                continue
            file_id = item.get("content_id")
            if not file_id or file_id in seen_ids:
                continue
            title = item.get("title") or ""
            seen_ids.add(file_id)
            try:
                file_meta = client.get_file_metadata(file_id)
            except Exception:
                continue

            filename = file_meta.get("display_name") or file_meta.get("filename") or ""
            if not _allowed_ext(filename):
                continue

            url = file_meta.get("url")
            if not url:
                continue

            label = filename
            if title and title != filename:
                label = f"{filename} (module: {title})"

            candidates.append({
                "name":       filename,
                "filename":   filename,
                "label":      label,
                "url":        url,
                "confidence": _score_candidate(filename, title),
            })
    return candidates


def _collect_module_candidates_debug(course_id: int | str, client) -> tuple[list[dict], str | None]:
    """Debug wrapper for module file discovery."""
    try:
        return _collect_module_candidates(course_id, client), None
    except Exception as exc:
        return [], str(exc)


def _ask_claude_pick_syllabus(candidates: list[dict]) -> str | None:
    """Ask Claude Haiku which file in candidates is most likely the syllabus.

    Passes the list of filenames and asks for the exact filename of the best
    match, or 'none' if nothing looks like a syllabus.  Returns the
    corresponding URL, or None.
    """
    claude = _get_anthropic_client()

    ranked_candidates = sorted(
        candidates,
        key=lambda c: (c["confidence"], c.get("filename", "")),
        reverse=True,
    )[:_LLM_PICK_CANDIDATE_LIMIT]
    names = "\n".join(f"- {c.get('label') or c['name']}" for c in ranked_candidates)
    prompt = (
        "The following files are available in a university course on Canvas LMS.\n"
        "Which ONE file is most likely to be the course syllabus or course outline "
        "(the document that lists grading breakdown, assessments, and policies)?\n\n"
        f"{names}\n\n"
        "Reply with ONLY the exact filename from the list above, or reply 'none' "
        "if none of the files look like a syllabus. No explanation."
    )

    message = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )

    chosen = message.content[0].text.strip().strip('"').strip("'")
    if chosen.lower() == "none":
        return None

    # Match the chosen name back to a URL
    for c in ranked_candidates:
        if c.get("label", c["name"]).lower() == chosen.lower():
            return c["url"]
        if c["name"].lower() == chosen.lower():
            return c["url"]

    # Fuzzy fallback: substring match
    for c in ranked_candidates:
        label = c.get("label", c["name"]).lower()
        name = c["name"].lower()
        if chosen.lower() in label or label in chosen.lower():
            return c["url"]
        if chosen.lower() in name or name in chosen.lower():
            return c["url"]

    return None


def _collect_syllabus_body_page_candidates(course_id: int | str, client) -> list[dict]:
    """Return Canvas page candidates linked directly from syllabus HTML."""
    try:
        syllabus = client.get_syllabus(course_id)
    except Exception:
        return []

    html = syllabus.get("syllabus_body") or ""
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    seen_slugs = set()
    candidates = []
    for a in soup.find_all("a", href=True):
        slug = _extract_page_slug(a["href"])
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        title = a.get_text(strip=True) or slug.replace("-", " ")
        candidates.append({
            "name": title,
            "label": title,
            "page_slug": slug,
            "source_type": "page",
            "confidence": _score_candidate(title, slug.replace("-", " ")),
        })
    return candidates


def _collect_module_page_candidates(course_id: int | str, client) -> list[dict]:
    """Return Canvas page candidates referenced from course modules."""
    try:
        modules = client.get_course_modules(course_id)
    except Exception:
        return []

    seen_slugs = set()
    candidates = []
    for module in modules:
        for item in module.get("items", []):
            if item.get("type") != "Page":
                continue
            slug = item.get("page_url") or _extract_page_slug(item.get("html_url") or "")
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            title = item.get("title") or slug.replace("-", " ")
            candidates.append({
                "name": title,
                "label": title,
                "page_slug": slug,
                "source_type": "page",
                "confidence": _score_candidate(title, slug.replace("-", " ")),
            })
    return candidates


def _collect_frontpage_page_candidates(course_id: int | str, client) -> list[dict]:
    """Return Canvas page candidates linked from the front page."""
    try:
        page = client.get_front_page(course_id)
    except Exception:
        return []

    html = page.get("body") or ""
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    seen_slugs = set()
    candidates = []
    for a in soup.find_all("a", href=True):
        slug = _extract_page_slug(a["href"])
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        title = a.get_text(strip=True) or slug.replace("-", " ")
        candidates.append({
            "name": title,
            "label": title,
            "page_slug": slug,
            "source_type": "page",
            "confidence": _score_candidate(title, slug.replace("-", " ")),
        })
    return candidates


def _pick_best_candidate(candidates: list[dict]) -> dict | None:
    """Deterministically choose a clear best candidate when possible.

    If one file is the unique top-ranked candidate with a positive score and
    every runner-up scores strictly lower, prefer it directly rather than
    asking the LLM to choose among mostly irrelevant files.
    """
    if not candidates:
        return None

    ranked = sorted(
        candidates,
        key=lambda c: (c["confidence"], c.get("filename", "")),
        reverse=True,
    )
    best = ranked[0]
    if best["confidence"] < _DIRECT_PICK_MIN_CONFIDENCE:
        return None

    if len(ranked) == 1:
        return best

    second = ranked[1]
    if best["confidence"] > second["confidence"]:
        return best

    return None


def find_syllabus_file(course_id: int | str, client) -> str | None:
    """Search for the most likely syllabus document in a course.

    Strategy
    --------
    1. Collect .pdf/.docx candidates from the course files API.
    2. Collect .pdf/.docx file items from course modules.
    3. Deduplicate by URL, score each by keyword confidence (0–1).
    4. If the best candidate confidence > _CONFIDENCE_THRESHOLD (0.3), return it.
    5. Otherwise pass the full candidate list to Claude Haiku to pick the best.
    6. Return None if nothing is found or Claude says 'none'.

    Parameters
    ----------
    course_id : Canvas course ID.
    client    : An authenticated QuercusClient instance.
    """
    # Collect from both sources and deduplicate by URL
    all_candidates: list[dict] = []
    seen_urls: set[str] = set()

    for c in _collect_file_candidates(course_id, client) + _collect_module_candidates(course_id, client):
        url = c.get("url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        all_candidates.append(c)

    if not all_candidates:
        return None

    # Sort by confidence descending
    all_candidates.sort(key=lambda x: x["confidence"], reverse=True)
    best = all_candidates[0]

    if best["confidence"] > _CONFIDENCE_THRESHOLD:
        return best["url"]

    direct_pick = _pick_best_candidate(all_candidates)
    if direct_pick is not None:
        return direct_pick["url"]

    # Low confidence across the board — let Claude decide
    return _ask_claude_pick_syllabus(all_candidates)


def find_syllabus_frontpage(course_id: int | str, client) -> str | None:
    """Search the course front page for a linked syllabus PDF.

    Fetches the course homepage via GET /courses/{id}/front_page, parses all
    anchor tags with BeautifulSoup, and scores each link by its *visible text*
    (e.g. "Course Outline", "Syllabus") rather than the filename — link text is
    far more reliable on UofT courses where files have opaque names.

    Only links pointing to Canvas files (/files/ or /download in the href) are
    considered; each is resolved to a direct download URL via the files API.
    The highest-scoring link whose confidence > 0 is returned.

    Parameters
    ----------
    course_id : Canvas course ID.
    client    : An authenticated QuercusClient instance.
    """
    try:
        page = client.get_front_page(course_id)
    except Exception:
        # 404 = no front page set; 401/403 = restricted — either way, skip
        return None

    html = page.get("body") or ""
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    candidates: list[dict] = []
    seen_ids: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Only Canvas file links
        if "/files/" not in href and "/download" not in href:
            continue

        match = re.search(r"/files/(\d+)", href)
        if not match:
            continue
        file_id = match.group(1)
        if file_id in seen_ids:
            continue
        seen_ids.add(file_id)

        # Score by visible link text, fall back to href filename
        link_text = a.get_text(strip=True) or ""
        score_text = link_text if link_text else href.rsplit("/", 1)[-1]
        conf = _confidence(score_text)

        try:
            url = client.get_file_download_url(file_id)
        except Exception:
            continue

        candidates.append({
            "name":       score_text,
            "url":        url,
            "confidence": conf,
        })

    if not candidates:
        return None

    candidates.sort(key=lambda x: x["confidence"], reverse=True)
    best = candidates[0]
    return best["url"] if best["confidence"] > 0 else None


def find_syllabus_page(course_id: int | str, client) -> dict | None:
    """Search for the most likely syllabus-like Canvas page in a course."""
    all_candidates: list[dict] = []
    seen_slugs: set[str] = set()

    for candidate in (
        _collect_syllabus_body_page_candidates(course_id, client)
        + _collect_module_page_candidates(course_id, client)
        + _collect_frontpage_page_candidates(course_id, client)
    ):
        slug = candidate.get("page_slug")
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        all_candidates.append(candidate)

    if not all_candidates:
        return None

    all_candidates.sort(key=lambda x: x["confidence"], reverse=True)
    best = all_candidates[0]
    if best["confidence"] > 0:
        return best
    return None




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
    claude = _get_anthropic_client()

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


def _extract_text_from_html(html: str) -> str:
    """Extract plain text from syllabus-like HTML content."""
    text = BeautifulSoup(html or "", "html.parser").get_text("\n", strip=True)
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not text:
        raise SyllabusError("Page contained no extractable text")
    return text


def _load_persisted_weights(course_id: int | str, source_ref: str) -> dict[str, float] | None:
    """Load parsed weights from Supabase if available."""
    try:
        weights = get_cached_syllabus_weights(course_id, source_ref)
    except SyllabusCacheError as exc:
        print(f"Syllabus cache lookup skipped: {exc}", flush=True)
        return None
    if weights:
        print(f"Syllabus cache hit: {course_id} [{source_ref}]", flush=True)
    return weights


def _save_persisted_weights(course_id: int | str, source_ref: str, weights: dict[str, float]) -> None:
    """Best-effort save of parsed weights to Supabase."""
    try:
        save_cached_syllabus_weights(course_id, source_ref, weights)
        print(f"Syllabus cache save: {course_id} [{source_ref}]", flush=True)
    except SyllabusCacheError as exc:
        print(f"Syllabus cache save skipped: {exc}", flush=True)


def parse_syllabus_weights(
    course_id: int | str,
    client,
    pdf_url: str = None,
) -> tuple[str, dict[str, float]]:
    """Cached wrapper around syllabus weight extraction."""
    cache_key = getattr(client, "_token_cache_key", "default")
    return _parse_syllabus_weights_cached(course_id, cache_key, client, pdf_url)


@st.cache_data(ttl=3600, show_spinner=False)
def _parse_syllabus_weights_cached(
    course_id: int | str,
    cache_key: str,
    _client,
    pdf_url: str = None,
) -> tuple[str, dict[str, float]]:
    """Extract grade weights from a course syllabus PDF.

    Resolution order
    ----------------
    1. Use pdf_url directly if provided (from syllabus_body HTML links).
    2. find_syllabus_file()      — course files API + modules API + Claude picker.
    3. find_syllabus_frontpage() — course homepage links scored by link text.

    Parameters
    ----------
    course_id : Canvas course ID.
    client    : An authenticated QuercusClient instance.
    pdf_url   : Pre-resolved download URL, or None to trigger the fallback chain.

    Returns
    -------
    (source_url, weights) — the URL that was actually parsed, and a dict
    mapping assessment component name to percentage weight.

    Raises
    ------
    SyllabusError if no PDF can be found through any strategy.
    """
    source_url = pdf_url

    if not source_url:
        source_url = find_syllabus_file(course_id, _client)

    if not source_url:
        source_url = find_syllabus_frontpage(course_id, _client)

    if not source_url:
        page_candidate = find_syllabus_page(course_id, _client)
        if page_candidate:
            source_ref = f"canvas-page:{page_candidate['page_slug']}"
            cached = _load_persisted_weights(course_id, source_ref)
            if cached:
                return source_ref, cached
            page = _client.get_page(course_id, page_candidate["page_slug"])
            text = _extract_text_from_html(page.get("body") or "")
            weights = _ask_claude(text)
            _save_persisted_weights(course_id, source_ref, weights)
            return source_ref, weights

    if not source_url:
        raise SyllabusError(
            f"No syllabus PDF found for course {course_id} "
            "(tried syllabus_body, files/modules/front page, and Canvas pages)"
        )

    cached = _load_persisted_weights(course_id, source_url)
    if cached:
        return source_url, cached

    pdf_bytes = _download_pdf(source_url)
    text = _extract_text(pdf_bytes)
    weights = _ask_claude(text)
    _save_persisted_weights(course_id, source_url, weights)

    return source_url, weights
