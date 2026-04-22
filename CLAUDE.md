# uoft-agent

An AI academic assistant for University of Toronto students.

## Live URLs

- Main app: `https://uoft-agent.com`
- Chrome extension: `https://chromewebstore.google.com/detail/akchfgkjeenfkmcommdpnimgkbnclgfa?utm_source=item-share-cb`

## What It Does

- Connects to Quercus with a student-provided personal access token
- Persists the Quercus token per logged-in user in Supabase after encrypting it with Fernet
- Computes current standing and target-grade scenarios with deterministic Python math
- Resolves course weights from Canvas assignment groups when available
- Falls back to syllabus discovery and Anthropic-based weight extraction when Canvas weights are missing
- Supports syllabi published as PDFs, DOCX files, or Canvas pages
- Imports ACORN academic history through a user-triggered Chrome extension and a small backend API
- The ACORN Chrome extension is published on the Chrome Web Store:
  https://chromewebstore.google.com/detail/akchfgkjeenfkmcommdpnimgkbnclgfa?utm_source=item-share-cb

## Architecture

- `app.py` — main Streamlit app and dashboard
- `auth/user_store.py` — Supabase-backed user lookup and encrypted Quercus token persistence
- `agent/` — Anthropic tool-calling loop, tool schemas, prompt
- `calculator/` — deterministic grade calculations and weighted-component modeling
- `integrations/quercus.py` — Canvas / Quercus API client
- `integrations/syllabus.py` — syllabus discovery, PDF parsing, and weight extraction
- `integrations/syllabus_cache.py` — persistent Supabase cache for parsed syllabus weights
- `integrations/acorn.py` — Streamlit-side ACORN backend client
- `api_server.py` — minimal ACORN import API backed by Supabase Postgres
- `uoft-acorn-extension/` — Manifest V3 Chrome extension for ACORN import, published on the Chrome Web Store
- `api/` — FastAPI backend powering the deployed app at `https://uoft-agent.com`
  - `api/main.py` — FastAPI app with CORS, mounts all routers, health check at `GET /`
  - `api/dependencies.py` — JWT-based `get_current_user` dependency
  - `api/routers/auth.py` — Google OAuth flow, JWT issuance (7-day expiry), `/auth/me`, `/auth/logout`
  - `api/routers/courses.py` — course, grade, scenario, weight routes + Quercus token CRUD
  - `api/routers/chat.py` — `POST /api/chat` runs agent via `run_in_executor`
  - `api/routers/acorn.py` — public ACORN routes matching `api_server.py` exactly
  - `api/services/course_service.py` — uncached Quercus + calculator wrappers (bypasses `st.cache_data`)
  - `api/services/acorn_service.py` — ACORN business logic for the FastAPI router
  - `api/services/auth_service.py` — user lookup/creation and JWT signing helpers
- `frontend/` — Vite + React frontend deployed at `https://uoft-agent.com`
  - `frontend/src/App.jsx` — app routes, protected shell, frontend auth callback handling
  - `frontend/src/api/client.js` — Axios client with JWT injection and 401 handling
  - `frontend/src/hooks/useAuth.jsx` — localStorage-backed auth state and login completion
  - `frontend/src/hooks/useQuercusStatus.jsx` — checks whether the logged-in user has a saved Quercus token
  - `frontend/src/components/` — reusable UI pieces including sidebar shell, profile menu, cards, lists, and tool-call rendering
  - `frontend/src/pages/` — Login, Quercus onboarding, Dashboard, Course Detail, Chat, and ACORN pages
  - `frontend/src/index.css` — shared design system, typography, layout, and animation styles

## Key Decisions

- No LangChain; native Anthropic tool calling only
- LLM handles orchestration and syllabus extraction, Python handles arithmetic
- The UI shows weighted grades only when the weighted component model is reliable enough
- Students provide their own Quercus token in the app; the validated token is encrypted and persisted in Supabase per user
- Session state still caches the active token and derived dashboard data for the current run
- Quercus submissions and assignment groups are cached briefly to speed up dashboard refreshes without making grades feel stale
- Parsed syllabus weights are cached both in-process and persistently in Supabase to avoid repeated Anthropic parsing for the same course source
- FastAPI course routes accept `?quercus_token=...` directly from the client; fall back to the Supabase-stored token if omitted
- `api/services/course_service.py` subclasses `QuercusClient` as `UncachedQuercusClient` to bypass `st.cache_data` decorators without touching the original integration files
- JWT secret stored in `JWT_SECRET` env var; Google OAuth credentials reuse `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
- FastAPI Google OAuth now redirects back to the React frontend using `FRONTEND_URL`, and the frontend stores the returned JWT in localStorage
- Swagger auth uses HTTP Bearer so developers can paste JWTs directly while testing the FastAPI API
- Production frontend is served at `https://uoft-agent.com`; backend CORS allows `FRONTEND_URL` and optional `CORS_ORIGINS`

## Auth

There are now two auth paths in the repo:

- Streamlit app: still uses Streamlit's native Google auth (`st.login("google")`, `st.user`, `st.logout()`)
- React + FastAPI app: uses FastAPI Google OAuth, then redirects to the frontend callback with a signed JWT

The new React auth flow is:

- frontend login button hits `GET /auth/google`
- FastAPI sends the user to Google
- Google returns to FastAPI at `REDIRECT_URI`
- FastAPI callback signs a JWT and redirects to `${FRONTEND_URL}/auth/callback?token=...`
- React stores the token in localStorage and uses it for protected API calls
- After Google auth, React checks for a saved Quercus token; users without one are sent to `/onboarding`

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
- `app.py` reads flat app secrets on the main thread and mirrors runtime values such as `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, and `ENCRYPTION_KEY` into `os.environ` for helper modules
- The app upserts the logged-in user by `st.user.sub` and stores encrypted Quercus tokens in the `quercus_tokens` table keyed by `user_id`

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
- `JWT_SECRET` for signing FastAPI JWTs (generate: `python -c "import secrets; print(secrets.token_hex(32))"`)
- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` for FastAPI Google OAuth
- `REDIRECT_URI` for FastAPI Google OAuth callback, e.g. `http://localhost:8001/auth/callback`
- `FRONTEND_URL` for the React app callback target, e.g. `http://localhost:5173`
- `CORS_ORIGINS` optional comma-separated extra allowed frontend origins for FastAPI CORS

## Current Status

Implemented:

- Quercus integration for courses, assignments, submissions, assignment groups, syllabus body, modules, files, grades, and announcements
- Persisted Quercus-token flow: load saved token on login, skip onboarding when present, allow manual disconnect, and clear revoked tokens automatically
- Dynamic current-term filtering using Canvas term metadata
- Dashboard with course cards, deadlines, announcements, chat, and a top-right feedback CTA
- Weighted grade calculations and dedicated per-course what-if pages
- Syllabus fallback that can discover files from syllabus HTML, modules, course files, front-page links, or linked Canvas pages
- More reliable module-based syllabus selection by preferring real file metadata and deterministically picking a unique best candidate before calling the LLM chooser
- Canvas page syllabus support for courses where the syllabus is published as a Quercus page instead of a file
- Short-lived Quercus caching: assignment groups and submissions are cached for 5 minutes
- Syllabus parsing cache: in-process cache for 1 hour plus persistent Supabase cache in `syllabus_weights_cache`
- ACORN import flow from the published Chrome extension to Railway-hosted backend to Streamlit readback
- ACORN imports can now be claimed to the logged-in user account so returning users do not need to re-import on every visit
- The Streamlit ACORN tab is behind the `ACORN_ENABLED` feature flag and, when enabled, shows either saved ACORN data or the onboarding / re-import flow
- Public privacy pages under `docs/` and extension privacy docs under `uoft-acorn-extension/`
- ACORN tab shows a summary table (Courses Imported, Total Credits, Cumulative GPA) and an Altair line chart of GPA over time with a Sessional / Cumulative toggle; chart uses adaptive Y-axis zoom and labelled data points
- ACORN data is structured per-term: the extension extracts term headings, sessional GPA, and cumulative GPA directly from the ACORN DOM and stores them in a `terms` top-level array alongside the flat `courses` list
- Extension parses `courseAverage` (the class average column) as a nullable field on each course, stored but not yet displayed
- Transfer credits (course codes ending in `***`) are captured from blocks not under a term heading and stored with `term: null`
- Course code regex handles all UofT campus formats: UTSC (4 letters + 2 digits, e.g. `CSCA08H3`), St. George / UTM (3 letters + 3 digits, e.g. `CSC490H1`, `ECO101H5`), and transfer placeholders (`CSCA***`)
- Credit corrections applied in the extension at parse time: CR/NCR courses with `0.00` credits are set to `0.50`; COP-prefix courses are always `0.00`
- Total Credits in the summary table excludes IPR (In Progress) and NGA (No Grade Available) courses — only earned credits are counted
- `background.js` detects stale-tab "Receiving end does not exist" errors (happen when the extension updates while an ACORN tab is already open) and surfaces a clear "Please reload the ACORN tab" message rather than using `chrome.scripting` dynamic injection, keeping permissions minimal
- FastAPI Google OAuth now works locally with `http://localhost:8001/auth/callback`, and the callback redirects into the React app
- FastAPI + React app is deployed at `https://uoft-agent.com`
- FastAPI protected routes now use Bearer JWT auth in Swagger UI instead of the broken password-flow form
- `GET /api/courses/dashboard` aggregates dashboard cards plus upcoming deadlines and recent announcements in one request
- `POST /api/chat` can use the saved Supabase Quercus token when `quercus_token` is omitted
- React frontend scaffolded with Vite, React Router, Axios, and TanStack Query
- React login page implemented and wired to FastAPI Google OAuth
- React Quercus onboarding flow implemented: checks for saved token, validates new token, persists it, and redirects into the app
- React dashboard implemented with course cards, upcoming deadlines rail, recent announcements section, and profile dropdown
- React course-detail page implemented with real grade breakdown data and what-if sliders
- React chat page implemented against `POST /api/chat` with tool-call blocks and suggestion chips
- Shared React app shell implemented with sidebar navigation for Dashboard, Chat, and ACORN
- React ACORN page implemented with onboarding/claim flow, summary cards, GPA chart, sortable course table, and re-import flow
- Frontend and backend deployment scaffolding added for Railway: `Procfile`, frontend Dockerfile, nginx static config, and production API URL support

Not implemented yet:

- React frontend polish and completion of remaining product flows
- Gradescope integration
- MarkUs integration
- ACORN-driven planning workflows beyond readback/import

## Known Constraints

- Courses with unresolved or only partially reliable syllabus-to-Canvas mappings intentionally show no weighted overview grade
- What-if sliders are only enabled when the weighted component model is reliable
- The ACORN backend still receives extension imports by import code first; the Streamlit app then claims the latest matching import to the logged-in user account
- Quercus token persistence requires a valid `ENCRYPTION_KEY` and Supabase tables compatible with the app's `users` and `quercus_tokens` queries
- Persistent syllabus caching requires a `syllabus_weights_cache` table in Supabase
- Quercus grade changes can take up to about 5 minutes to appear because submissions and assignment groups are cached for 300 seconds
- The React frontend currently stores the FastAPI JWT in localStorage; this is expedient for development but not the final hardened auth posture

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

Run the FastAPI backend (dev):

```bash
uvicorn api.main:app --reload --port 8001
```

Swagger UI available at `http://localhost:8001/docs`.

Run the React frontend (dev):

```bash
cd frontend
npm install
npm run dev
```

Vite frontend available at `http://localhost:5173`.
