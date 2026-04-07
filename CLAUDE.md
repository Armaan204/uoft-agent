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
  pages (Co-op Compass, Undergrads, etc.) excluded
- Syllabus weight extraction via three-stage fallback:
  `syllabus_body` PDF link → modules/files API search → front page links
  (MUZA99 and EESA10 resolving correctly via modules; STAC51 outline
  not uploaded to Quercus — front page fallback in progress)
- Grade calculator — current weighted grade, needed score, letter-grade
  scenarios; pure Python, no LLM
- Agent loop with native Claude API function calling (no LangChain)
- Streamlit chat UI with tool-call expanders (`streamlit run app.py`)

**Not yet started:**
- ACORN integration (transcript, GPA)
- Gradescope and MarkUs integrations
