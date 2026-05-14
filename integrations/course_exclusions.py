"""
integrations/course_exclusions.py — Cross-campus course exclusion lookup.

Fetches and caches the Exclusion field from UofT academic calendar pages so
that the graduation matcher can recognise cross-campus equivalencies.

Public API:
  fetch_exclusions_batch(codes: list[str]) -> dict[str, set[str]]
    Async; returns {normalized_code: set_of_excluded_codes}.
    Reads Supabase cache first; fetches missing codes in parallel.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone

import httpx
from supabase import create_client

# ---------------------------------------------------------------------------
# Calendar URL prefixes
# ---------------------------------------------------------------------------

_UTSC_BASE = "https://utsc.calendar.utoronto.ca/course"
_UTM_BASE  = "https://utm.calendar.utoronto.ca/course"
_ARTSCI_BASES = [
    "https://artsci.calendar.utoronto.ca/course",
    "https://daniels.calendar.utoronto.ca/course",
    "https://engineering.calendar.utoronto.ca/course",
    "https://music.calendar.utoronto.ca/course",
    "https://kpe.calendar.utoronto.ca/course",
    "https://pharmacy.calendar.utoronto.ca/course",
]

# Matches all UofT campus course codes:
#   UTSC   e.g. CSCA08H3  (4-letter dept + 2-digit + H/Y + 3)
#   UTM    e.g. CSC108H5  (3-letter dept + 3-digit + H/Y + 5)
#   ArtsCI e.g. CSC108H1  (3-letter dept + 3-digit + H/Y + 1)
_COURSE_CODE_RE = re.compile(r'\b([A-Z]{3,4}\d{2,3}[HY][0-9])\b')

# Section headings that mark the end of the Exclusion block
_SECTION_STOP_RE = re.compile(
    r'\b(Breadth\s+Requirements?|Distribution\s+Requirements?|Hours|Notes?:|'
    r'Prerequisite[s]?|Corequisite[s]?|Recommended\s+Preparation|Credit\s+Value|'
    r'Contact\s+Hours|Learning\s+Outcomes?|Programme\s+Notes?)\b',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(code: str) -> str:
    return code.strip().upper()


def _campus_urls(code: str) -> list[str]:
    """Return ordered candidate URLs for a course code, campus-detected from suffix."""
    m = re.search(r'[HY](\d)$', code)
    suffix = m.group(1) if m else ""
    lc = code.lower()
    if suffix == "3":
        return [f"{_UTSC_BASE}/{lc}"]
    if suffix == "5":
        return [f"{_UTM_BASE}/{lc}"]
    # H1/Y1/H0/Y0 or unknown → try all St. George faculties in order
    return [f"{base}/{lc}" for base in _ARTSCI_BASES]


def _strip_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>",  "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _extract_exclusions(text: str) -> set[str]:
    """Parse the Exclusion section from a calendar page's plain text."""
    m = re.search(r'\bExclusion[s]?\b', text, re.IGNORECASE)
    if not m:
        return set()
    after = text[m.end():]
    stop = _SECTION_STOP_RE.search(after)
    section = after[: stop.start()] if stop else after[:600]
    return {hit.group(1).upper() for hit in _COURSE_CODE_RE.finditer(section)}


# ---------------------------------------------------------------------------
# Supabase cache
# ---------------------------------------------------------------------------

def _db():
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


def _load_cache(codes: list[str]) -> dict[str, set[str]]:
    if not codes:
        return {}
    try:
        resp = (
            _db()
            .table("course_exclusions_cache")
            .select("course_code, exclusions")
            .in_("course_code", codes)
            .execute()
        )
        return {
            row["course_code"]: set(row.get("exclusions") or [])
            for row in (getattr(resp, "data", None) or [])
        }
    except Exception:
        return {}


def _save_cache(entries: list[tuple[str, set[str], str | None]]) -> None:
    if not entries:
        return
    try:
        _db().table("course_exclusions_cache").upsert(
            [
                {
                    "course_code":  code,
                    "exclusions":   sorted(excl),
                    "calendar_url": url,
                    "cached_at":    datetime.now(timezone.utc).isoformat(),
                }
                for code, excl, url in entries
            ],
            on_conflict="course_code",
        ).execute()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Async HTTP fetch
# ---------------------------------------------------------------------------

async def _fetch_one(
    code: str, client: httpx.AsyncClient
) -> tuple[str, set[str], str | None]:
    """Try each candidate URL for *code* and return (code, exclusions, url)."""
    for url in _campus_urls(code):
        try:
            r = await client.get(url, timeout=12.0, follow_redirects=True)
            if r.status_code == 200:
                return code, _extract_exclusions(_strip_html(r.text)), url
        except Exception:
            continue
    return code, set(), None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_exclusions_batch(codes: list[str]) -> dict[str, set[str]]:
    """
    Return {normalized_code: set_of_excluded_codes} for every code in *codes*.
    Hits the Supabase cache first; fetches remaining codes in parallel via httpx.
    """
    normalized = [_normalize(c) for c in codes if c]
    if not normalized:
        return {}

    result = _load_cache(normalized)
    missing = [c for c in normalized if c not in result]

    if missing:
        async with httpx.AsyncClient() as client:
            fetched = await asyncio.gather(
                *[_fetch_one(c, client) for c in missing],
                return_exceptions=True,
            )

        to_save: list[tuple[str, set[str], str | None]] = []
        for item in fetched:
            if isinstance(item, Exception):
                continue
            code, excl, url = item
            result[code] = excl
            to_save.append((code, excl, url))

        if to_save:
            await asyncio.to_thread(_save_cache, to_save)

    return result
