<div align="center">

# UofT Agent

AI academic assistant for University of Toronto students.

</div>

## Live App

https://uoft-agent.streamlit.app/

## What It Does

UofT Agent combines live academic data, deterministic grade math, and an Anthropic tool-calling loop.

Current capabilities:

- Quercus course retrieval
- Assignment and submission retrieval
- Canvas assignment-group weight resolution
- Syllabus PDF discovery and weight extraction when Canvas weights are missing
- Current-grade and target-grade calculations
- Dashboard cards, announcements, deadlines, and per-course what-if views
- ACORN academic-history import via browser extension and backend API

## Core Flow

1. The student signs in with Google using Streamlit's native auth.
2. The student enters a Quercus personal access token.
3. The app loads current courses and grade data from Quercus.
4. If Canvas weights are missing, the app searches for a syllabus and extracts weights with Anthropic.
5. Deterministic Python code computes grades and scenarios.
6. The chat agent can call the same tools to answer natural-language questions.

## Project Structure

- [`app.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/app.py) — Streamlit UI, dashboard, chat, ACORN tab
- [`agent/agent.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/agent/agent.py) — Anthropic agent loop
- [`agent/tools.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/agent/tools.py) — tool schemas and dispatch
- [`calculator/grades.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/calculator/grades.py) — deterministic grade engine
- [`integrations/quercus.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/integrations/quercus.py) — Quercus / Canvas API client
- [`integrations/syllabus.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/integrations/syllabus.py) — syllabus discovery and parsing
- [`api_server.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/api_server.py) — ACORN import backend
- [`uoft-acorn-extension/`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/uoft-acorn-extension) — Chrome extension

## Auth

The app uses Streamlit's built-in auth APIs:

- `st.login("google")`
- `st.user`
- `st.logout()`

This is not a Supabase Auth flow and not a custom auth module.

On Streamlit Cloud, configure secrets like this:

```toml
ANTHROPIC_API_KEY = "..."
SUPABASE_URL = "..."
SUPABASE_KEY = "..."
ENCRYPTION_KEY = "..."

[auth]
redirect_uri = "https://uoft-agent.streamlit.app/oauth2callback"
cookie_secret = "..."

[auth.google]
client_id = "..."
client_secret = "..."
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

Important:

- App secrets such as `ANTHROPIC_API_KEY` must stay at the top level
- Do not place them under `[auth]` or `[auth.google]`

## Local Development

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a local `.env`:

```env
ANTHROPIC_API_KEY=your_anthropic_key
QUERCUS_API_TOKEN=your_quercus_token
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_service_role_key
ENCRYPTION_KEY=your_fernet_key
```

Run the Streamlit app:

```bash
streamlit run app.py
```

Run the ACORN backend locally:

```bash
python api_server.py
```

## Deployment

Recommended split:

- Streamlit app on Streamlit Cloud
- ACORN backend on Railway
- ACORN import storage in Supabase Postgres

The backend supports:

- `POST /api/acorn/import`
- `GET /api/acorn/latest?import_code=...`
- `GET /api/acorn/status?import_code=...`

The Railway entrypoint is [`Procfile`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/Procfile):

```text
web: python api_server.py
```

## Notes On Grade Resolution

- Canvas `group_weight` is preferred whenever it exists
- Syllabus parsing is a fallback for courses with incomplete LMS metadata
- Weighted overview grades are shown only when the component mapping is reliable enough
- Module-based syllabus discovery now prefers actual file metadata and can deterministically select a unique best candidate before falling back to an LLM chooser

## Current Limitations

- Gradescope and MarkUs integrations are still placeholders
- Some courses intentionally show no weighted overview grade when syllabus-to-assignment mapping is too ambiguous
- ACORN import currently uses import codes rather than a full user account model

## License

MIT. See [`LICENSE`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/LICENSE).
