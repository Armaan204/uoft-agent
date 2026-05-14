"""
integrations/graduation_service.py — Graduation planning service.

Public API:
  get_program_requirements(acorn_name, force_refresh=False) -> dict | None
  check_graduation_progress(requirements, acorn_data) -> dict
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from datetime import datetime, timezone

import anthropic
import requests
from supabase import create_client

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CALENDAR_BASES = {
    "UTSC":   "https://utsc.calendar.utoronto.ca",
    "UTM":    "https://utm.calendar.utoronto.ca",
    "ARTSCI": "https://artsci.calendar.utoronto.ca",
}

_UNEARNED_GRADES = {"IPR", "NGA", "LWD", "NCR", "GWR", "SDF", "WD"}


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

def _db():
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

def _llm():
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _current_academic_year() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year}-{now.year + 1}" if now.month >= 9 else f"{now.year - 1}-{now.year}"

def _load_cache(acorn_name: str) -> dict | None:
    key = acorn_name.lower().strip()
    try:
        resp = _db().table("program_requirements_cache") \
            .select("requirements, extraction_status") \
            .eq("acorn_name", key).limit(1).execute()
        rows = getattr(resp, "data", None) or []
        if rows and rows[0].get("extraction_status") == "ok" and rows[0].get("requirements"):
            return rows[0]["requirements"]
    except Exception:
        pass
    return None

def _save_cache(
    acorn_name: str,
    canonical_name: str,
    program_code: str | None,
    campus: str,
    calendar_url: str,
    requirements: dict,
    academic_year: str,
) -> None:
    key = acorn_name.lower().strip()
    try:
        _db().table("program_requirements_cache").upsert({
            "acorn_name":      key,
            "canonical_name":  canonical_name,
            "program_code":    program_code,
            "campus":          campus,
            "calendar_url":    calendar_url,
            "requirements":    requirements,
            "academic_year":   academic_year,
            "extraction_status": "ok",
            "extraction_error":  None,
            "extracted_at":    datetime.now(timezone.utc).isoformat(),
        }, on_conflict="acorn_name").execute()
    except Exception:
        pass

def _save_failed(acorn_name: str, error: str) -> None:
    key = acorn_name.lower().strip()
    try:
        _db().table("program_requirements_cache").upsert({
            "acorn_name":        key,
            "academic_year":     _current_academic_year(),
            "extraction_status": "failed",
            "extraction_error":  error,
            "extracted_at":      datetime.now(timezone.utc).isoformat(),
        }, on_conflict="acorn_name").execute()
    except Exception:
        pass

def clear_cache(acorn_name: str) -> None:
    """Remove a cached entry so it will be re-extracted on next request."""
    key = acorn_name.lower().strip()
    try:
        _db().table("program_requirements_cache").delete().eq("acorn_name", key).execute()
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Campus detection
# ---------------------------------------------------------------------------

def _detect_campus(program_name: str) -> str:
    low = program_name.lower()
    if any(k in low for k in ["utm", "mississauga", "erindale"]):
        return "UTM"
    if any(k in low for k in ["artsci", "st. george", "trinity", "victoria"]):
        return "ARTSCI"
    return "UTSC"

# ---------------------------------------------------------------------------
# URL discovery
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    text = re.sub(r"\s+", "-", text.strip())
    return re.sub(r"-+", "-", text).strip("-")

_COURSE_CODE_RE = re.compile(r'\b[A-Z]{3}[A-Z]\d{2}[HY]3\b')

# Words that carry no program-identity signal; stripped when building URL keywords.
_SLUG_STOP_WORDS = frozenset({
    "specialist", "co", "operative", "coop", "program", "programs",
    "in", "of", "the", "and", "or", "for", "stream", "major", "minor",
    "certificate", "science", "arts", "degree",
})

# Prepositions dropped by UTSC's URL slug generator ("in", "of", etc.
# but NOT "and" — that is kept, e.g. "machine-learning-and-data-science").
_UTSC_SLUG_PREPOSITIONS = frozenset({"in", "of", "at", "for", "by", "with", "from", "to"})

# Known UTSC calendar program renames that change the URL slug.
# These are cases where the ACORN name differs from the current calendar name.
_UTSC_SLUG_RENAMES: list[tuple[str, str]] = [
    ("data-mining", "data-science"),   # SML stream renamed circa 2023-24
]

def _has_course_requirements(text: str) -> bool:
    """Return True only if the page contains 3+ specific course codes."""
    return len(_COURSE_CODE_RE.findall(text)) >= 3

def _program_url_keywords(name: str) -> list[str]:
    """
    Extract meaningful subject words from a program name for URL validation.
    E.g. 'Specialist (Co-op) Program in Statistics - Data Mining Stream'
    → ['statistics', 'data', 'mining']
    """
    words = re.findall(r'[a-z]+', name.lower())
    return [w for w in words if w not in _SLUG_STOP_WORDS and len(w) > 3]

def _slugify_utsc(name: str) -> str:
    """
    Slugify a program name following UTSC calendar URL conventions:
    - Expand parenthetical content, preserving internal hyphens (Co-operative → co-operative)
    - Drop trailing separator hyphens (Statistics- → statistics)
    - Drop prepositions (in, of, …) but keep conjunctions (and)
    - Join remaining words with hyphens
    """
    name = name.lower()
    name = re.sub(r'\(([^)]+)\)', lambda m: m.group(1), name)  # expand parens
    name = re.sub(r'-(?=\s|$)', ' ', name)                      # drop trailing hyphens
    name = re.sub(r'[^a-z0-9-]+', ' ', name)                   # punct → space
    words = [w.strip('-') for w in name.split()
             if w.strip('-') and w.strip('-') not in _UTSC_SLUG_PREPOSITIONS]
    return '-'.join(w for w in words if w)

def _generate_utsc_slug_variants(name: str) -> list[str]:
    """Return all plausible UTSC calendar URL slug variants for a program name."""
    base = _slugify_utsc(name)
    variants: list[str] = [base]

    # Strip program code suffix (scspe1234y, scspm5678m, …)
    no_code = re.sub(r'-scs[a-z]{2}\d{4,}[a-z]?$', '', base)
    if no_code != base:
        variants.append(no_code)

    # Strip trailing designation suffixes some programs append
    for suffix in ('-science', '-arts', '-music'):
        for v in list(variants):
            if v.endswith(suffix):
                variants.append(v[:-len(suffix)])

    # Apply known program renames (both directions caught by the list)
    extended: list[str] = []
    for v in variants:
        for old, new in _UTSC_SLUG_RENAMES:
            if old in v:
                extended.append(v.replace(old, new))
    variants.extend(extended)

    # Deduplicate, preserving order
    seen: set[str] = set()
    return [v for v in variants if v and not (v in seen or seen.add(v))]  # type: ignore[func-returns-value]


def _fetch_page(url: str) -> dict | None:
    """Fetch url and return {"url", "text", "html"} or None on error/non-200."""
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            return None
        html = r.text
        text = _html_to_text(html)
        return {"url": url, "text": text, "html": html}
    except Exception:
        return None

def _is_valid_program_page(page: dict, is_coop: bool = False, keywords: list[str] | None = None) -> bool:
    """
    Accept a page if it has actual course requirements, OR if it is a
    co-op page that:
      - has 'co-operative' in its URL, AND
      - at least one program subject keyword appears in the URL
        (rules out the generic 'co-operative-programs' overview page).
    """
    if _has_course_requirements(page["text"]):
        return True
    if is_coop and "co-operative" in page["url"].lower():
        if keywords:
            url_lower = page["url"].lower()
            if any(kw in url_lower for kw in keywords):
                return True
        else:
            return True  # no keywords available — fall back to old behaviour
    return False

def _find_base_specialist_url(coop_url: str, base_domain: str) -> str | None:
    """
    Derive the base (non-co-op) specialist/major page URL from a co-op program URL.
    UTSC co-op pages do not link to their base programs, so we probe directly:
      1. Strip 'co-operative-' from the slug
      2. Try with and without common discipline suffixes (-science, -arts, -music)
      3. Accept the first URL whose page contains 3+ course codes
    """
    slug = coop_url.rstrip("/").split("/")[-1]
    base_slug = re.sub(r'\bco-operative-', '', slug)
    if base_slug == slug:
        return None  # wasn't actually a co-op URL

    # Strip program code suffix, if present
    no_code = re.sub(r'-scs[a-z]{2}\d{4,}[a-z]?$', '', base_slug)

    candidates: list[str] = list(dict.fromkeys([
        base_slug,
        base_slug + "-science",
        base_slug + "-arts",
        base_slug + "-music",
        no_code,
        no_code + "-science",
        no_code + "-arts",
    ]))

    for cand in candidates:
        if not cand:
            continue
        page = _fetch_page(f"{base_domain}/{cand}")
        if page and _has_course_requirements(page["text"]):
            return f"{base_domain}/{cand}"
    return None

def _ddg_search_urls(query: str, base_domain: str) -> list[str]:
    """Search DuckDuckGo HTML and return result URLs that are on base_domain."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        r = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=headers,
            timeout=15,
        )
        if r.status_code != 200:
            return []
        # DDG wraps actual URLs in redirect links: href="/l/?uddg=<url-encoded-url>&..."
        encoded = re.findall(r'uddg=(https?%3A%2F%2F[^&"]+)', r.text)
        results = []
        for enc in encoded:
            url = urllib.parse.unquote(enc)
            if base_domain in url:
                results.append(url)
        return results
    except Exception:
        return []

def _anthropic_web_search_url(program_name: str, base: str) -> str | None:
    """
    Use Anthropic's built-in web_search tool with a proper multi-turn loop.
    Returns the first calendar URL found, or None.
    Times out after 30 s total to avoid blocking the request.
    """
    import anthropic as _anthropic_module
    import httpx

    base_domain = base.split("//")[1].rstrip("/")
    client = _anthropic_module.Anthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        timeout=httpx.Timeout(30.0, connect=5.0),
    )
    messages: list[dict] = [{
        "role": "user",
        "content": (
            f'Find the exact UTSC academic calendar page URL for this program: '
            f'"{program_name}". The URL must start with {base}. '
            f'Return ONLY the full URL, nothing else.'
        ),
    }]

    for _ in range(5):  # max 5 turns (search → result → answer)
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=messages,
            )
        except Exception:
            return None

        # Harvest any calendar URL from text blocks
        for block in response.content:
            text = getattr(block, "text", "") or ""
            for m in re.finditer(r'https?://\S+', text):
                url = m.group(0).rstrip(".,;)'\"")
                if base_domain in url:
                    return url

        if response.stop_reason != "tool_use":
            break

        # Continue the loop: tell the API to execute the tool call
        messages.append({"role": "assistant", "content": response.content})
        tool_results = [
            {"type": "tool_result", "tool_use_id": block.id, "content": ""}
            for block in response.content
            if getattr(block, "type", "") == "tool_use"
        ]
        if not tool_results:
            break
        messages.append({"role": "user", "content": tool_results})

    return None

def _discover_url_via_web_search(program_name: str, base: str, is_coop: bool) -> dict | None:
    """
    Search online for the exact calendar URL.
    Tries Anthropic's native web_search tool (with proper loop + timeout) first,
    then DuckDuckGo as a fallback.
    """
    base_domain = base.split("//")[1].rstrip("/")

    url = _anthropic_web_search_url(program_name, base)
    if url:
        page = _fetch_page(url)
        if page:
            return page

    # --- DuckDuckGo fallback ---
    for query in [
        f'site:{base_domain} "{program_name}"',
        f'site:{base_domain} {program_name}',
    ]:
        for url in _ddg_search_urls(query, base_domain):
            page = _fetch_page(url)
            if page:
                return page

    return None

def _discover_url_via_slug(program_name: str, base: str, is_coop: bool, keywords: list[str]) -> dict | None:
    """
    Probe UTSC calendar URL slug variants directly.
    Deterministic variants (based on UTSC URL conventions + known renames) are
    tried first; LLM-generated extras are tried as a bonus.
    HEAD pre-check is skipped — just GET directly to avoid servers that 405 on HEAD.
    """
    deterministic = _generate_utsc_slug_variants(program_name)

    # Ask LLM for additional candidates beyond the deterministic ones
    llm_slugs: list[str] = []
    try:
        msg = _llm().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": (
                f'UTSC academic calendar program: "{program_name}"\n\n'
                "Generate 5 URL slugs for this program's specific calendar page.\n"
                "UTSC slug rules:\n"
                "- Lowercase, words joined by hyphens\n"
                "- Drop prepositions 'in'/'of' but keep 'and'\n"
                "- '(Co-operative)' → 'co-operative'; '(SCIENCE)' may be omitted\n"
                "- Stream name may be RENAMED in the calendar (e.g. 'Data Mining' "
                "→ 'Data Science', 'Applied Statistics' → 'Statistics')\n"
                "- Generate variants for both the original and any likely renamed version\n\n"
                "Output ONLY a JSON array of 5 slug strings, nothing else."
            )}],
        )
        raw = re.sub(r"```[a-z]*|```", "", msg.content[0].text).strip()
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            llm_slugs = [s for s in parsed if isinstance(s, str)]
    except Exception:
        pass

    seen: set[str] = set()
    all_slugs = [s for s in deterministic + llm_slugs
                 if s and not (s in seen or seen.add(s))]  # type: ignore[func-returns-value]

    for slug in all_slugs[:12]:
        page = _fetch_page(f"{base}/{slug}")
        if page and _is_valid_program_page(page, is_coop, keywords):
            return page
    return None

def _discover_calendar_url(program_name: str, campus: str, is_coop: bool) -> dict | None:
    """
    Returns {"url","text","html"} for the best-matching program page, or None.
    Tries two strategies in order:
      1. Slug probe — deterministic UTSC slug generation + LLM variants (fast, no external calls)
      2. Web search — Anthropic web_search tool with multi-turn loop, then DuckDuckGo
                      (handles renames and unusual URL patterns without any hardcoding)
    """
    base = _CALENDAR_BASES.get(campus, _CALENDAR_BASES["UTSC"])
    keywords = _program_url_keywords(program_name)

    result = _discover_url_via_slug(program_name, base, is_coop, keywords)
    if result:
        return result
    return _discover_url_via_web_search(program_name, base, is_coop)

# ---------------------------------------------------------------------------
# Page fetching
# ---------------------------------------------------------------------------

def _html_to_text(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>",  "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()

# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------

_EXTRACTION_SYSTEM = (
    "You are an expert at extracting structured academic program requirements "
    "from university calendar pages. Output ONLY valid JSON, no explanation, no markdown fences."
)

_SCHEMA_HINT = """
Output this JSON structure exactly (omit inapplicable keys):

{
  "program_code": "SCSPE2289Y or null",
  "program_name": "canonical name from the calendar",
  "calendar_url": "page URL",
  "academic_year": "2025-2026",
  "campus": "UTSC or UTM or ARTSCI",
  "is_coop": true,
  "program_credits_required": 13.0,
  "degree_credits_required": 20.0,
  "double_counting": {"within_program": false, "program_vs_degree_breadth": true},
  "groups": [
    {
      "id": "snake_case_unique_id",
      "label": "Human-readable section label",
      "section": "core or stream",
      "credits_required": 2.5,
      "items": [
        {"id": "unique_id", "type": "required",
         "courses": ["CSCA08H3"], "credits": 0.5, "label": "Intro CS I"},
        {"id": "unique_id", "type": "required",
         "courses": ["MATA67H3","CSCA67H3"], "credits": 0.5,
         "label": "Discrete Math (either)"},
        {"id": "unique_id", "type": "n_credits_from_list",
         "credits_needed": 0.5, "courses": ["ANTA01H3","CTLA01H3"],
         "label": "0.5 cr from approved writing list"},
        {"id": "unique_id", "type": "open_pool",
         "credits_needed": 1.5,
         "label": "1.5 cr C/D-level CSC/MAT/STA (min 1.0 STA)",
         "filters": {"departments": ["CSC","MAT","STA"], "levels": ["C","D"]},
         "exclusions": ["STAC32H3","STAC53H3"],
         "sub_requirements": [
           {"id": "sta_min", "label": "Min 1.0 STA",
            "departments": ["STA"], "levels": ["C","D"], "min_credits": 1.0}
         ]}
      ]
    }
  ],
  "coop": {
    "work_terms_required": 3,
    "total_months": 12,
    "note": "co-op note",
    "preparation":       [{"id": "copb50", "type": "required", "courses": ["COPB50H3"]}],
    "search_courses":    [{"id": "wts1",   "type": "required", "courses": ["COPB57H3","COPB52H3"],
                           "note": "before 1st work term"}],
    "work_term_courses": [{"id": "wt1",    "type": "required", "courses": ["COPC01H3"]}]
  }
}

RULES:
- "required": take exactly one course from courses[] (handles OR alternatives)
- "n_credits_from_list": earn N credits from the explicit list
- "open_pool": earn N credits from courses matching department+level filters
- H3 = 0.5 credits, Y3 = 1.0 credit
- group credits_required must equal sum of item credits values
- omit "coop" key entirely for non-co-op programs
- UTSC course format: [3-letter dept][level A/B/C/D][2 digits][H/Y]3
"""

def _extract_with_llm(page_text: str, calendar_url: str, coop_text: str | None = None) -> dict:
    content = page_text[:15000]
    if coop_text:
        content += "\n\n--- CO-OP SPECIFIC REQUIREMENTS ---\n\n" + coop_text[:4000]

    prompt = (
        f"Extract all graduation requirements from this academic calendar page.\n\n"
        f"Calendar URL: {calendar_url}\n\n"
        f"{_SCHEMA_HINT}\n\n"
        f"Page content:\n{content}"
    )
    msg = _llm().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=_EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = re.sub(r"```[a-z]*|```", "", msg.content[0].text).strip()
    result = json.loads(raw)
    if not isinstance(result, dict) or "groups" not in result:
        raise ValueError("LLM returned invalid schema — missing 'groups' key")
    return result

# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def get_program_requirements(acorn_name: str, force_refresh: bool = False) -> dict | None:
    """
    Return structured program requirements for acorn_name.
    Checks Supabase cache first; on miss discovers the calendar URL,
    fetches the page, and extracts requirements with Claude.
    Returns None if the program cannot be found or extracted.
    """
    if force_refresh:
        clear_cache(acorn_name)
    else:
        cached = _load_cache(acorn_name)
        if cached:
            return cached

    campus = _detect_campus(acorn_name)
    is_coop = "co-operative" in acorn_name.lower() or "co-op" in acorn_name.lower()

    # Discover URL; pass is_coop so co-op pages (which have no course codes) are accepted.
    discovered = _discover_calendar_url(acorn_name, campus, is_coop)
    if not discovered:
        _save_failed(acorn_name, "Could not discover calendar URL with valid course requirements")
        return None
    url       = discovered["url"]
    page_text = discovered["text"]
    raw_html  = discovered["html"]

    # Co-op pages defer academic requirements to the base specialist page.
    # UTSC co-op pages do not link back to their base program, so we derive
    # the base URL by stripping "co-operative-" from the slug and probing.
    coop_supplement: str | None = None
    canonical_url = url
    if is_coop:
        base_domain = "/".join(url.rstrip("/").split("/")[:-1])
        base_url = _find_base_specialist_url(url, base_domain)
        if base_url:
            base_page = _fetch_page(base_url)
            if base_page and _has_course_requirements(base_page["text"]):
                coop_supplement = page_text         # co-op page → supplement
                page_text       = base_page["text"] # base specialist → primary
                canonical_url   = base_url

    try:
        requirements = _extract_with_llm(page_text, canonical_url, coop_supplement)
    except Exception as exc:
        _save_failed(acorn_name, f"LLM extraction failed: {exc}")
        return None

    if is_coop:
        requirements["is_coop"] = True

    _save_cache(
        acorn_name=acorn_name,
        canonical_name=requirements.get("program_name", acorn_name),
        program_code=requirements.get("program_code"),
        campus=campus,
        calendar_url=url,
        requirements=requirements,
        academic_year=requirements.get("academic_year", _current_academic_year()),
    )
    return requirements

# ---------------------------------------------------------------------------
# Exclusion-based equivalency
# ---------------------------------------------------------------------------

def collect_required_courses(requirements: dict) -> list[str]:
    """
    Return every course code that appears in a 'required' or 'n_credits_from_list'
    item across all requirement groups.  Used by the router to know which required
    courses to pre-fetch exclusions for.
    """
    codes: list[str] = []
    for group in requirements.get("groups", []):
        for item in group.get("items", []):
            if item.get("type") in ("required", "n_credits_from_list"):
                codes.extend(item.get("courses", []))
    return codes


def _campus_digit(code: str) -> str | None:
    """Return the campus digit from a UofT course code suffix (H1→'1', H3→'3', H5→'5'), or None."""
    m = re.search(r'[HY](\d)$', code)
    return m.group(1) if m else None


def _satisfies_via_exclusion(
    taken_code: str,
    required_code: str,
    exclusions_map: dict[str, set[str]],
) -> bool:
    """
    True if taken_code and required_code are cross-campus equivalents recognised
    via the calendar Exclusion field.  Checks both directions:
      1. required_code appears in taken_code's exclusion list
      2. taken_code appears in required_code's exclusion list

    Same-campus exclusions (both codes share the same campus digit) are intentionally
    excluded — those are credit-conflict rules ("can't take both"), not equivalencies.
    """
    if taken_code == required_code:
        return False
    t_digit = _campus_digit(taken_code)
    r_digit = _campus_digit(required_code)
    if t_digit and r_digit and t_digit == r_digit:
        return False  # same campus — not a cross-campus equivalency
    if required_code in exclusions_map.get(taken_code, set()):
        return True
    if taken_code in exclusions_map.get(required_code, set()):
        return True
    return False


# ---------------------------------------------------------------------------
# Matching algorithm
# ---------------------------------------------------------------------------

def _course_credits(course: dict) -> float:
    try:
        val = float(course.get("credits") or 0.5)
        return val if val > 0 else 0.5
    except (TypeError, ValueError):
        return 0.5

# Maps the first digit of a St. George/UTM 3-digit course number to its UTSC level letter.
# 100-level → A, 200-level → B, 300-level → C, 400-level → D.
_NUMERIC_LEVEL_MAP = {'1': 'A', '2': 'B', '3': 'C', '4': 'D'}


def _parse_dept_level(code: str) -> tuple[str, str] | None:
    """Return (department, level-letter) for any UofT course code, or None.

    UTSC codes use a 4-letter dept where position 3 is the level letter:
      CSCA08H3 → ('CSC', 'A'),  STAC33H3 → ('STA', 'C')

    St. George / UTM codes use a 3-letter dept + 3-digit number whose first
    digit encodes the level (1→A, 2→B, 3→C, 4→D):
      CSC300H1 → ('CSC', 'C'),  STA302H1 → ('STA', 'C'),  MAT401H5 → ('MAT', 'D')
    """
    if len(code) < 5:
        return None
    if code[:3].isalpha() and code[3].isalpha():
        # UTSC-style: 4-letter dept, level is the 4th character
        return code[:3].upper(), code[3].upper()
    if code[:3].isalpha() and code[3].isdigit():
        # St. George / UTM-style: 3-letter dept, level from first digit of course number
        level = _NUMERIC_LEVEL_MAP.get(code[3])
        if level:
            return code[:3].upper(), level
    return None

def _matches_filter(code: str, departments: set, levels: set, exclusions: set) -> bool:
    if code in exclusions:
        return False
    parsed = _parse_dept_level(code)
    return parsed is not None and parsed[0] in departments and parsed[1] in levels

def check_graduation_progress(
    requirements: dict,
    acorn_data: dict,
    exclusions_map: dict[str, set[str]] | None = None,
) -> dict:
    """
    Match ACORN courses against program requirements.
    Each course is assigned to at most one requirement (no double counting within program).

    exclusions_map — optional {course_code: set_of_excluded_codes} pre-fetched by the
    caller; when provided, cross-campus equivalents are recognised via bidirectional
    exclusion checks so e.g. CSC108H1 can satisfy a CSCA08H3 requirement.

    Returns {overall_status, credits_satisfied, credits_in_progress, credits_remaining, groups, coop}.
    """
    # Build completed / in-progress sets from ACORN terms
    completed: dict[str, dict] = {}
    in_progress: set[str] = set()

    raw_courses: list[dict] = []
    for term in acorn_data.get("terms", []):
        raw_courses.extend(term.get("courses", []))
    if not raw_courses:
        raw_courses = acorn_data.get("courses", [])

    for course in raw_courses:
        code = (course.get("code") or course.get("courseCode") or "").strip().upper()
        if not code:
            continue
        grade = (course.get("grade") or "").strip().upper()
        credits = _course_credits(course)
        if grade == "IPR":
            in_progress.add(code)
        elif grade and grade not in _UNEARNED_GRADES and grade != "F":
            try:
                mark = float(course.get("mark") or 50)
            except (TypeError, ValueError):
                mark = 50
            if mark >= 50:
                completed[code] = {"grade": grade, "credits": credits}

    used: set[str] = set()
    excl = exclusions_map or {}
    group_results = []

    for group in requirements.get("groups", []):
        group_results.append(_match_group(group, completed, in_progress, used, excl))

    coop_result = None
    if requirements.get("is_coop") and requirements.get("coop"):
        coop_result = _match_coop(requirements["coop"], completed, in_progress, used, excl)

    total_req = float(requirements.get("program_credits_required") or 13.0)
    total_sat = sum(g["credits_satisfied"] for g in group_results)
    total_ip  = sum(g["credits_in_progress"] for g in group_results)

    all_sat = all(g["status"] == "satisfied" for g in group_results)
    any_ip  = any(g["status"] == "in_progress" for g in group_results)
    overall = "satisfied" if all_sat else ("in_progress" if any_ip else "remaining")

    return {
        "program_name":            requirements.get("program_name"),
        "academic_year":           requirements.get("academic_year"),
        "campus":                  requirements.get("campus"),
        "is_coop":                 requirements.get("is_coop", False),
        "program_credits_required": total_req,
        "degree_credits_required": float(requirements.get("degree_credits_required") or 20.0),
        "credits_satisfied":       round(total_sat, 2),
        "credits_in_progress":     round(total_ip,  2),
        "credits_remaining":       round(max(0.0, total_req - total_sat), 2),
        "overall_status":          overall,
        "groups":                  group_results,
        "coop":                    coop_result,
    }

# ---------------------------------------------------------------------------
# Group / item matching helpers
# ---------------------------------------------------------------------------

def _match_group(
    group: dict,
    completed: dict,
    in_progress: set,
    used: set,
    exclusions_map: dict[str, set[str]] | None = None,
) -> dict:
    items = group.get("items", [])
    # Most constrained first: required + n_credits_from_list before open_pool
    priority = [i for i in items if i.get("type") != "open_pool"]
    pools    = [i for i in items if i.get("type") == "open_pool"]

    results_map: dict[str, dict] = {}
    for item in priority + pools:
        t = item.get("type")
        if t == "required":
            r = _match_required(item, completed, in_progress, used, exclusions_map)
        elif t == "n_credits_from_list":
            r = _match_n_credits_list(item, completed, in_progress, used, exclusions_map)
        elif t == "open_pool":
            r = _match_open_pool(item, completed, in_progress, used)
        else:
            r = {"id": item.get("id"), "type": t, "status": "unknown",
                 "credits_satisfied": 0.0, "credits_in_progress": 0.0}
        results_map[item.get("id")] = r

    ordered = [results_map[i.get("id")] for i in items if i.get("id") in results_map]
    sat = sum(r.get("credits_satisfied", 0.0) for r in ordered)
    ip  = sum(r.get("credits_in_progress", 0.0) for r in ordered)
    req = float(group.get("credits_required") or 0.0)

    status = "satisfied" if sat >= req else ("in_progress" if sat + ip >= req else "remaining")
    return {
        "id":               group["id"],
        "label":            group["label"],
        "section":          group.get("section", ""),
        "credits_required": req,
        "credits_satisfied":   round(sat, 2),
        "credits_in_progress": round(ip,  2),
        "status":           status,
        "items":            ordered,
    }


def _match_required(
    item: dict,
    completed: dict,
    in_progress: set,
    used: set,
    exclusions_map: dict[str, set[str]] | None = None,
) -> dict:
    courses = item.get("courses", [])
    credits = float(item.get("credits") or 0.5)

    # Direct completed match
    for code in courses:
        if code in completed and code not in used:
            used.add(code)
            return {
                "id": item["id"], "type": "required", "label": item.get("label"),
                "credits_satisfied": credits, "credits_in_progress": 0.0,
                "status": "satisfied", "satisfied_by": [code],
            }

    # Cross-campus exclusion match (completed)
    if exclusions_map:
        for req_code in courses:
            for taken_code in completed:
                if taken_code not in used and _satisfies_via_exclusion(taken_code, req_code, exclusions_map):
                    used.add(taken_code)
                    return {
                        "id": item["id"], "type": "required", "label": item.get("label"),
                        "credits_satisfied": credits, "credits_in_progress": 0.0,
                        "status": "satisfied", "satisfied_by": [taken_code],
                        "satisfied_via_exclusion": req_code,
                    }

    # Direct in-progress match
    for code in courses:
        if code in in_progress and code not in used:
            return {
                "id": item["id"], "type": "required", "label": item.get("label"),
                "credits_satisfied": 0.0, "credits_in_progress": credits,
                "status": "in_progress", "in_progress_by": [code],
            }

    # Cross-campus exclusion match (in-progress)
    if exclusions_map:
        for req_code in courses:
            for taken_code in in_progress:
                if taken_code not in used and _satisfies_via_exclusion(taken_code, req_code, exclusions_map):
                    return {
                        "id": item["id"], "type": "required", "label": item.get("label"),
                        "credits_satisfied": 0.0, "credits_in_progress": credits,
                        "status": "in_progress", "in_progress_by": [taken_code],
                        "in_progress_via_exclusion": req_code,
                    }

    return {
        "id": item["id"], "type": "required", "label": item.get("label"),
        "credits_satisfied": 0.0, "credits_in_progress": 0.0,
        "status": "remaining", "courses_needed": courses,
    }


def _match_n_credits_list(
    item: dict,
    completed: dict,
    in_progress: set,
    used: set,
    exclusions_map: dict[str, set[str]] | None = None,
) -> dict:
    needed     = float(item.get("credits_needed") or 0.5)
    course_set = set(item.get("courses", []))
    sat = 0.0
    ip  = 0.0
    sat_by: list[str] = []
    ip_by:  list[str] = []

    for list_code in sorted(course_set):
        if sat >= needed:
            break
        # Direct completed match
        if list_code in completed and list_code not in used:
            cr = completed[list_code]["credits"]
            used.add(list_code)
            sat += cr
            sat_by.append(list_code)
            continue
        # Cross-campus exclusion match (completed)
        if exclusions_map:
            for taken_code, info in completed.items():
                if taken_code not in used and _satisfies_via_exclusion(taken_code, list_code, exclusions_map):
                    used.add(taken_code)
                    sat += info["credits"]
                    sat_by.append(taken_code)
                    break

    for list_code in sorted(course_set):
        if sat + ip >= needed:
            break
        # Direct in-progress match
        if list_code in in_progress and list_code not in used:
            ip += 0.5
            ip_by.append(list_code)
            continue
        # Cross-campus exclusion match (in-progress)
        if exclusions_map:
            for taken_code in in_progress:
                if taken_code not in used and _satisfies_via_exclusion(taken_code, list_code, exclusions_map):
                    ip += 0.5
                    ip_by.append(taken_code)
                    break

    sat = min(sat, needed)
    status = "satisfied" if sat >= needed else (
        "in_progress" if sat + ip >= needed else "remaining"
    )
    return {
        "id": item["id"], "type": "n_credits_from_list", "label": item.get("label"),
        "credits_needed": needed,
        "credits_satisfied":   round(sat, 2),
        "credits_in_progress": round(ip,  2),
        "status": status,
        "satisfied_by": sat_by,
        "in_progress_by": ip_by,
    }


def _match_open_pool(item: dict, completed: dict, in_progress: set, used: set) -> dict:
    needed      = float(item.get("credits_needed") or 0.0)
    filters     = item.get("filters", {})
    departments = set(filters.get("departments", []))
    levels      = set(filters.get("levels", []))
    exclusions  = set(item.get("exclusions", []))
    sub_reqs    = item.get("sub_requirements", [])

    eligible_c = {
        code: info for code, info in completed.items()
        if _matches_filter(code, departments, levels, exclusions) and code not in used
    }
    eligible_ip = {
        code for code in in_progress
        if _matches_filter(code, departments, levels, exclusions) and code not in used
    }

    pool_sat:    float     = 0.0
    pool_ip:     float     = 0.0
    pool_sat_by: list[str] = []
    pool_ip_by:  list[str] = []
    sub_results: list[dict] = []

    # Satisfy sub-requirements first (greedy), then fill the general pool
    for sr in sub_reqs:
        sr_depts  = set(sr.get("departments", []))
        sr_levels = set(sr.get("levels", []))
        sr_min    = float(sr.get("min_credits") or 0.0)
        sr_sat = 0.0; sr_ip = 0.0
        sr_sat_by: list[str] = []; sr_ip_by: list[str] = []

        for code in sorted(eligible_c):
            if sr_sat >= sr_min or pool_sat >= needed:
                break
            parsed = _parse_dept_level(code)
            if parsed and parsed[0] in sr_depts and parsed[1] in sr_levels:
                cr = eligible_c.pop(code)["credits"]
                used.add(code)
                pool_sat += cr; sr_sat += cr
                pool_sat_by.append(code); sr_sat_by.append(code)

        for code in sorted(eligible_ip):
            if sr_sat + sr_ip >= sr_min or pool_sat + pool_ip >= needed:
                break
            parsed = _parse_dept_level(code)
            if parsed and parsed[0] in sr_depts and parsed[1] in sr_levels:
                eligible_ip.discard(code)
                pool_ip += 0.5; sr_ip += 0.5
                pool_ip_by.append(code); sr_ip_by.append(code)

        sr_status = "satisfied" if sr_sat >= sr_min else (
            "in_progress" if sr_sat + sr_ip >= sr_min else "remaining"
        )
        sub_results.append({
            "id": sr["id"], "label": sr.get("label"),
            "min_credits": sr_min,
            "credits_satisfied":   round(sr_sat, 2),
            "credits_in_progress": round(sr_ip,  2),
            "status": sr_status,
            "satisfied_by": sr_sat_by,
            "in_progress_by": sr_ip_by,
        })

    # Fill remaining pool capacity with any still-eligible courses
    for code in sorted(eligible_c):
        if pool_sat >= needed:
            break
        cr = eligible_c[code]["credits"]
        used.add(code)
        pool_sat += cr
        pool_sat_by.append(code)

    for code in sorted(eligible_ip):
        if pool_sat + pool_ip >= needed:
            break
        pool_ip += 0.5
        pool_ip_by.append(code)

    pool_sat = min(pool_sat, needed)
    status   = "satisfied" if pool_sat >= needed else (
        "in_progress" if pool_sat + pool_ip >= needed else "remaining"
    )
    return {
        "id": item["id"], "type": "open_pool", "label": item.get("label"),
        "credits_needed": needed,
        "credits_satisfied":   round(pool_sat, 2),
        "credits_in_progress": round(pool_ip,  2),
        "status": status,
        "satisfied_by":   pool_sat_by,
        "in_progress_by": pool_ip_by,
        "sub_requirements": sub_results,
    }


def _match_coop(
    coop: dict,
    completed: dict,
    in_progress: set,
    used: set,
    exclusions_map: dict[str, set[str]] | None = None,
) -> dict:
    sections = {
        "preparation":       coop.get("preparation", []),
        "search_courses":    coop.get("search_courses", []),
        "work_term_courses": coop.get("work_term_courses", []),
    }
    results: dict[str, list] = {}
    for name, items in sections.items():
        results[name] = [
            _match_required(item, completed, in_progress, used, exclusions_map)
            for item in items
        ]

    done = sum(1 for r in results.get("work_term_courses", []) if r.get("status") == "satisfied")
    req  = int(coop.get("work_terms_required") or 3)
    return {
        "work_terms_required":  req,
        "work_terms_completed": done,
        "work_terms_status": "satisfied" if done >= req else (
            "in_progress" if done > 0 else "remaining"
        ),
        **results,
    }
