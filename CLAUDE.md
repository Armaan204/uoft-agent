# uoft-agent

An AI academic assistant for University of Toronto students.

## What It Does

- Connects to Quercus with a student-provided personal access token
- Computes current standing and target-grade scenarios with deterministic Python math
- Resolves course weights from Canvas assignment groups when available
- Falls back to syllabus discovery and Anthropic-based weight extraction when Canvas weights are missing
- Imports ACORN academic history through a user-triggered Chrome extension and a small backend API

## Architecture

- `app.py` — main Streamlit app and dashboard
- `agent/` — Anthropic tool-calling loop, tool schemas, prompt
- `calculator/` — deterministic grade calculations and weighted-component modeling
- `integrations/quercus.py` — Canvas / Quercus API client
- `integrations/syllabus.py` — syllabus discovery, PDF parsing, and weight extraction
- `integrations/acorn.py` — Streamlit-side ACORN backend client
- `api_server.py` — minimal ACORN import API backed by Supabase Postgres
- `uoft-acorn-extension/` — Manifest V3 Chrome extension for ACORN import

## Key Decisions

- No LangChain; native Anthropic tool calling only
- LLM handles orchestration and syllabus extraction, Python handles arithmetic
- The UI shows weighted grades only when the weighted component model is reliable enough
- Students provide their own Quercus token in the app; it is stored only in Streamlit session state

## Auth

The app uses Streamlit's native authentication API:

- `st.login("google")`
- `st.user`
- `st.logout()`

Google OAuth is configured through Streamlit auth secrets, not Supabase Auth and not a custom auth module.

Expected Streamlit secrets structure:

```toml
ANTHROPIC_API_KEY = "..."
SUPABASE_URL = "..."
SUPABASE_KEY = "..."
ENCRYPTION_KEY = "..."

[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "..."

[auth.google]
client_id = "..."
client_secret = "..."
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

Important:

- Keep flat app secrets such as `ANTHROPIC_API_KEY` at the top level
- Do not place them under `[auth]` or `[auth.google]`
- `app.py` reads `ANTHROPIC_API_KEY` from `st.secrets` on the main thread and mirrors it into `os.environ` so worker-thread syllabus parsing can still access it

## Environment Variables

Local `.env` support is for development only.

Common variables:

- `ANTHROPIC_API_KEY`
- `QUERCUS_API_TOKEN` for local scripts only
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `ENCRYPTION_KEY`
- `ACORN_BACKEND_URL` optional override for the hosted ACORN API
- `HOST` and `PORT` for `api_server.py`

## Current Status

Implemented:

- Quercus integration for courses, assignments, submissions, assignment groups, syllabus body, modules, files, grades, and announcements
- Dynamic current-term filtering using Canvas term metadata
- Dashboard with course cards, deadlines, announcements, chat, and ACORN tab
- Weighted grade calculations and dedicated per-course what-if pages
- Syllabus fallback that can discover files from syllabus HTML, modules, course files, or the front page
- More reliable module-based syllabus selection by preferring real file metadata and deterministically picking a unique best candidate before calling the LLM chooser
- ACORN import flow from Chrome extension to Railway-hosted backend to Streamlit readback
- Public privacy pages under `docs/` and extension privacy docs under `uoft-acorn-extension/`

Not implemented yet:

- Gradescope integration
- MarkUs integration
- ACORN-driven planning workflows beyond readback/import

## Known Constraints

- Courses with unresolved or only partially reliable syllabus-to-Canvas mappings intentionally show no weighted overview grade
- What-if sliders are only enabled when the weighted component model is reliable
- The ACORN backend uses import-code scoping rather than a full user account model

## Local Usage

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the Streamlit app:

```bash
streamlit run app.py
```

Run the ACORN backend:

```bash
python api_server.py
```
