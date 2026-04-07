# uoft-agent

An AI agent for University of Toronto students. Uses tool-calling
(Claude API function calling) to answer academic questions in natural
language.

## What it does

- Fetches live data from Quercus (Canvas API) and ACORN
- Extracts grade weights from unstructured syllabi
- Answers questions like "what do I need on the final to pass?"
- Plans to support Gradescope and MarkUs in future

## Architecture

- `agent/` — agent loop, tool definitions, prompts
- `integrations/` — one file per platform (quercus, acorn, etc.)
- `calculator/` — pure Python grade math, no LLM involved
- `app.py` — Streamlit entry point

## Key decisions

- No LangChain — native Claude API function calling only
- LLM does reasoning, Python does all arithmetic
- Tool results fed back into agent loop before final answer
- grade weights parsed from syllabus when not available via API

## Environment variables

ANTHROPIC_API_KEY
QUERCUS_API_TOKEN
ACORN_USERNAME
ACORN_PASSWORD

## Current status

Core pipeline working end-to-end. Streamlit UI running locally.

**Done:**
- Quercus integration complete — courses, assignments, submissions,
  assignment groups, syllabus body, files, and grade enrollment
- Course list filtered to current term (2026 Winter) with resource
  pages excluded
- Grade weight resolution: Canvas `group_weight` used directly when
  non-zero (preferred, no LLM needed); falls back to three-stage
  syllabus parsing — `syllabus_body` PDF → modules/files search →
  front page links
- Fuzzy keyword matching in `_match_weight()` handles mismatches
  between Canvas group names and syllabus weight labels (e.g.
  "MIDTERM TEST" ↔ "Mid-term Examination")
- Grade calculator verified correct for EESA10, STAD68, and MUZA99 —
  current grade, needed score on final, and letter-grade scenarios
- Agent loop with native Claude API function calling (no LangChain)
- Streamlit chat UI with tool-call expanders (`streamlit run app.py`)

- Token onboarding screen in Streamlit — token validated via `get_courses()`
  on connect, stored in session state only (never written to disk)
- Token threaded from session state → `run()` → `execute_tool()` →
  `QuercusClient(token=...)` — no hardcoded env dependency in the UI

- Streamlit dashboard (loads before chat) with per-course summary cards:
  - Parallel data loading via `concurrent.futures.ThreadPoolExecutor`
  - Grade display uses accumulated grade: earned pts + full credit on
    ungraded work (i.e. "start at 100%, subtract marks lost so far")
  - Progress bar and risk flag (Safe ≥85%, On track 70–84%, At risk <70%)
  - "Grade breakdown" expander on every card:
    - Weighted courses: per-group earned/possible → pts contributed,
      plus "Remaining (X%): not yet assessed → X pts assumed" row;
      zero-weight items filtered out
    - Total-points courses: per-group earned/possible pts with merged
      duplicate group names, total shown explicitly
  - Total-points fallback (`_grade_from_points`) used when Canvas has
    no group weights and syllabus parsing is unavailable; duplicate
    Canvas group names merged (not overwritten) so breakdown matches total
  - Upcoming deadlines (next 14 days) across all courses, sorted by date
  - Refresh button clears session cache and reloads

**Known gap:**
- STAC51 course outline not on Quercus (files API 403, no front page,
  no syllabus-like files in modules) — total-points fallback used instead
- `get_grade_scenarios` bug fixed: groups with no assignments posted yet
  (e.g. FINAL EXAM before the assignment is created) are now correctly
  treated as ungraded rather than skipped

**Not yet started:**
- ACORN integration (transcript, GPA)
- Gradescope and MarkUs integrations
