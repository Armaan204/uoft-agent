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

Core pipeline is implemented and end-to-end tested.

**Working:**
- `integrations/quercus.py` — full `QuercusClient` with `get_courses`,
  `get_assignments`, `get_submissions`, `get_assignment_groups`,
  `get_syllabus`, `get_course_files`, `get_file_download_url`, `get_grades`
- `integrations/syllabus.py` — PDF discovery (`find_syllabus_file` with
  keyword scoring), PDF download, pypdf text extraction, Claude Haiku weight
  parsing; falls back to file search when `syllabus_body` has no PDF link
- `calculator/grades.py` — `GradeCalculator` with `current_grade`,
  `needed_on_final`, `grade_scenarios`; pure Python, no LLM
- `agent/tools.py` — four Claude tool schemas (`get_courses`,
  `get_course_weights`, `get_current_grade`, `get_grade_scenarios`) with
  full dispatch implementations
- `agent/agent.py` — multi-turn agent loop using native Claude API function
  calling; CLI entry point via `python -m agent.agent`
- `agent/prompts.py` — system prompt

**Tested on:**
- STAD68 (428033): syllabus weights extracted from PDF, current grade
  computed (100% on graded work), grade scenarios calculated correctly
- STAC51 (427986): assignments and submissions fetched; syllabus PDF not
  yet accessible (course file listing returns 403)

**Not yet implemented:**
- `app.py` Streamlit UI
- `integrations/acorn.py` (ACORN scraper)
- `integrations/gradescope.py`, `integrations/markus.py`
- `calculator/syllabus.py` weight normalisation helpers
