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

- `uoft-acorn-extension/` — Manifest V3 Chrome extension for ACORN import, published on the Chrome Web Store
- `api/` — entire Python backend powering the deployed app at `https://uoft-agent.com`
  - `api/main.py` — FastAPI app with CORS, mounts all routers, health check at `GET /`
  - `api/dependencies.py` — JWT-based `get_current_user` dependency
  - `api/routers/auth.py` — Google OAuth flow, JWT issuance (7-day expiry), `/auth/me`, `/auth/logout`
  - `api/routers/courses.py` — course, grade, scenario, weight routes + Quercus token CRUD
  - `api/routers/chat.py` — `POST /api/chat` runs agent via `run_in_executor`, persists exchanges by `conversation_id`, and exposes chat-history list/detail/delete routes
  - `api/routers/acorn.py` — public ACORN routes
  - `api/routers/graduation.py` — `GET /api/graduation/progress` and `DELETE /api/graduation/cache`
  - `api/services/course_service.py` — uncached Quercus + calculator wrappers
  - `api/services/grade_snapshot_cache.py` — 5-minute in-memory per-user cache for aggregate semester grade snapshots used by chat tools
  - `api/services/grades_snapshot_service.py` — Supabase-backed persistence layer for dashboard and course detail snapshots; `grades_snapshot` table stores `dashboard_data`, `announcements`, and `course_detail_data` JSONB columns per `(user_id, course_id)` row
  - `api/services/acorn_service.py` — ACORN business logic for the FastAPI router
  - `api/services/auth_service.py` — user lookup/creation and JWT signing helpers
  - `api/agent/` — Anthropic tool-calling loop, tool schemas, prompt
  - `api/auth/user_store.py` — Supabase-backed user lookup and encrypted Quercus token persistence
  - `api/calculator/` — deterministic grade calculations and weighted-component modeling
  - `api/integrations/quercus.py` — Canvas / Quercus API client
  - `api/integrations/syllabus.py` — syllabus discovery, PDF parsing, and weight extraction
  - `api/integrations/syllabus_cache.py` — persistent Supabase cache for parsed syllabus weights
  - `api/integrations/acorn_store.py` — ACORN import payload validation and file storage
  - `api/integrations/grades_cache.py` — Supabase-backed grade override and saved-grade persistence
  - `api/integrations/graduation_service.py` — graduation planning service: URL discovery, LLM-based requirements extraction, and course matching
- `frontend/` — Vite + React frontend deployed at `https://uoft-agent.com`
  - `frontend/src/App.jsx` — app routes, protected shell, frontend auth callback handling
  - `frontend/src/api/client.js` — Axios client with JWT injection and 401 handling
- `frontend/src/hooks/useAuth.jsx` — localStorage-backed auth state and login completion
- `frontend/src/hooks/useQuercusStatus.jsx` — checks whether the logged-in user has a saved Quercus token
- `frontend/src/components/` — reusable UI pieces including sidebar shell, profile menu, cards, lists, and tool-call rendering
- `frontend/src/pages/` — Login, Quercus onboarding, Dashboard, Course Detail, Chat, ACORN, and Degree Planner pages
- `frontend/src/index.css` — shared design system, typography, layout, and animation styles, including the sticky chat composer and inline course-grade editing states

## Key Decisions

- No LangChain; native Anthropic tool calling only
- LLM handles orchestration and syllabus extraction, Python handles arithmetic
- The UI shows weighted grades only when the weighted component model is reliable enough
- Students provide their own Quercus token in the app; the validated token is encrypted and persisted in Supabase per user
- Session state still caches the active token and derived dashboard data for the current run
- Quercus submissions and assignment groups are cached briefly to speed up dashboard refreshes without making grades feel stale
- Parsed syllabus weights are cached both in-process and persistently in Supabase to avoid repeated Anthropic parsing for the same course source
- Chat uses a cached aggregate grade snapshot tool for multi-course questions; the cache is keyed per user and can be explicitly refreshed
- UofT GPA mapping is deterministic in code (`A+` and `A` both map to `4.0`) rather than inferred by the LLM
- FastAPI course routes accept `?quercus_token=...` directly from the client; fall back to the Supabase-stored token if omitted
- Dashboard and course grade data use a 3-tier cache: (1) per-user in-memory Python dict (instant, lost on restart), (2) Supabase `grades_snapshot` JSONB snapshot (fast, survives restarts), (3) live Quercus fetch (slow, only on first load or force refresh). Each tier fires a background refresh to keep the next load fast.
- On every authenticated app load, `App.jsx` fires a background `GET /api/courses/dashboard` and staggered per-course `GET /api/courses/{id}/grades` requests to keep the Supabase snapshot current, so incognito and new-device loads hit Layer 2 instead of Layer 3
- The frontend uses `PersistQueryClientProvider` with a localStorage persister (24h `gcTime` and `maxAge`) so TanStack Query cache survives tab refreshes and browser restarts
- Manual dashboard refresh fetches directly and calls `setQueryData` on completion so existing data (including announcements) stays visible the entire time the refresh is in flight
- Grade overrides immediately update both the in-memory cache and Supabase snapshot so overridden grades are reflected on all subsequent cache hits
- `api/services/course_service.py` subclasses `QuercusClient` as `UncachedQuercusClient` to bypass any caching decorators on the base client methods
- JWT secret stored in `JWT_SECRET` env var; Google OAuth credentials reuse `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
- FastAPI Google OAuth now redirects back to the React frontend using `FRONTEND_URL`, and the frontend stores the returned JWT in localStorage
- The React chat page now keeps the active in-progress conversation and unsent draft in browser `sessionStorage`, keyed per logged-in user and conversation ID, so refreshes within the tab keep the live thread without persisting it across browser restarts
- Swagger auth uses HTTP Bearer so developers can paste JWTs directly while testing the FastAPI API
- Production frontend is served at `https://uoft-agent.com`; backend CORS allows `FRONTEND_URL` and optional `CORS_ORIGINS`
- Graduation planning uses a three-step pipeline: (1) URL discovery via UTSC-convention slug generation with a multi-turn Anthropic web_search fallback, (2) LLM extraction of structured requirements from the calendar page, (3) greedy matching of ACORN courses against requirements with no double-counting within the program
- For co-op programs the co-op overlay page is found first, then the base specialist page is derived by stripping `co-operative-` from the URL slug and probing variants (with/without `-science` suffix); the base page provides the academic requirements and the co-op page provides the work-term supplement
- Requirements are cached per `acorn_name` in the `program_requirements_cache` Supabase table; the Degree Planner page never auto-refetches (all TanStack Query auto-refetch options disabled) to avoid burning API credits
- Three requirement types: `required` (OR alternatives), `n_credits_from_list` (earn N credits from a list), `open_pool` (earn N credits from courses matching department+level filters, with optional sub-requirements)
- Co-op status is tracked as satisfied/in_progress/remaining; course matching is greedy with most-constrained requirements first

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
- Agent now has aggregate semester-grade tools: `get_all_grades` uses a cached per-user snapshot and `refresh_grades` forces a fresh pull
- React frontend scaffolded with Vite, React Router, Axios, and TanStack Query
- React login page implemented and wired to FastAPI Google OAuth
- React Quercus onboarding flow implemented: checks for saved token, validates new token, persists it, and redirects into the app
- React dashboard implemented with course cards, upcoming deadlines rail, recent announcements section, and profile dropdown; loads instantly on repeat visits via 3-tier server cache + TanStack localStorage persistence
- React course-detail page implemented with real grade breakdown data and what-if sliders; graded components can expand into individual Quercus assessments when a syllabus weight maps to a broader bucket
- React course-detail page now supports inline per-component score adjustments backed by persisted grade overrides; default score cells remain read-only until the user enters edit mode
- React chat page implemented against `POST /api/chat` with tool-call blocks, suggestion chips, and Markdown-style rendering for assistant responses
- React chat live-thread state now uses `sessionStorage` with a frontend `conversationId` and a `New chat` reset boundary
- FastAPI chat now accepts `conversation_id`, persists successful exchanges to Supabase-backed `chat_conversations` / `chat_messages`, and exposes history list/detail/delete endpoints
- Chat context is threaded into every request: `POST /api/chat` loads the prior 10 messages for the conversation from Supabase and passes them to the agent as history, enabling follow-up questions within the same thread; the agent caps history at 10 messages (5 exchanges) to stay within context limits
- React chat history is implemented as a dedicated `/chat/history` route with resume/delete flows; resumed conversations load under `/chat/:conversationId`
- React chat composer is now sticky at the bottom of the page while the message list scrolls independently
- React dashboard announcements now open an in-app modal that lazy-loads the full announcement body, with a fallback link to open the original Quercus announcement
- Shared React app shell implemented with sidebar navigation for Dashboard, Chat, and ACORN
- React ACORN page implemented with onboarding/claim flow, summary cards, GPA chart, sortable course table, and re-import flow
- Frontend and backend deployment scaffolding added for Railway: `Procfile`, frontend Dockerfile, nginx static config, and production API URL support
- Degree Planner page (`/degree-planner`) implemented: fetches graduation progress from `/api/graduation/progress`, shows program credit summary with progress bar, collapsible requirement groups, and a Re-analyze button that clears the cache and re-extracts

Not implemented yet:

- React frontend polish and completion of remaining product flows
- Chat history polish such as rename support and any further navigation / UX refinement
- UTM and St. George program support in the Degree Planner: the graduation pipeline currently only discovers and extracts UTSC calendar pages. When adding support for UTM (`utm.calendar.utoronto.ca`) or St. George (`artsci.calendar.utoronto.ca`) programs, two changes are required:
  1. **Extraction prompt** (`integrations/graduation_service.py` → `_SCHEMA_HINT`): add an explicit instruction that `open_pool` level filters must always be expressed as UTSC letter notation (`A`/`B`/`C`/`D`) regardless of how the calendar phrases it — UTSC calendars say "C-level", but UTM/St. George calendars say "300-level". Without this instruction the LLM may extract `levels: ["3","4"]` instead of `["C","D"]`, causing all open-pool level comparisons to silently fail.
  2. **`_parse_dept_level`** already handles the student-course side: non-UTSC codes like `CSC300H1` are mapped to `('CSC', 'C')` via `_NUMERIC_LEVEL_MAP`. No change needed there.
     The extraction-side normalization (point 1) is the only remaining gap before UTM/St. George program requirements can be correctly matched against a student's courses.

## Known Constraints

- Courses with unresolved or only partially reliable syllabus-to-Canvas mappings intentionally show no weighted overview grade
- What-if sliders are only enabled when the weighted component model is reliable
- The ACORN backend still receives extension imports by import code first; the Streamlit app then claims the latest matching import to the logged-in user account
- Quercus token persistence requires a valid `ENCRYPTION_KEY` and Supabase tables compatible with the app's `users` and `quercus_tokens` queries
- Persistent syllabus caching requires a `syllabus_weights_cache` table in Supabase
- Quercus grade changes can take up to about 5 minutes to appear because submissions and assignment groups are cached for 300 seconds
- The React frontend currently stores the FastAPI JWT in localStorage; this is expedient for development but not the final hardened auth posture
- Backend chat history requires the Supabase schema in `docs/chat_history_schema.sql` to be applied before list/detail/delete routes and persistence-backed history are available

## Tests

Run the test suite with coverage:

```bash
python -m coverage run -m pytest tests/ -q
python -m coverage report
```

Coverage is at near 100% overall. Key test files:

- `tests/test_agent.py` — `agent/agent.py` `run()` loop and `_extract_text()`
- `tests/test_acorn_store.py` — `integrations/acorn_store.py` payload validation, file I/O
- `tests/test_acorn_service.py` — `api/services/acorn_service.py` Supabase ACORN service
- `tests/test_chat_router.py` — `api/routers/chat.py` all route handlers
- `tests/test_encryption_and_syllabus_cache.py` — `integrations/encryption.py` and `integrations/syllabus_cache.py`
- `tests/test_snapshot_and_history.py` — `api/services/grades_snapshot_service.py` and `api/services/chat_history_service.py`
- `tests/test_grades_cache_and_auth.py` — `integrations/grades_cache.py`, `api/services/auth_service.py`, `api/dependencies.py`, `api/services/grade_snapshot_cache.py`

Notes:

- All external calls are mocked (no real Supabase, Anthropic, or HTTP)
- `asyncio_mode = auto` in `pytest.ini` — async test methods need no decorator
- Starlette 1.0 + FastAPI 0.103 TestClient is broken; route handlers are called directly as Python functions/coroutines
- `# pragma: no cover` is used on compatibility shims in `conftest.py` and on post-`asyncio.get_event_loop().run_until_complete()` assertion lines where Python 3.11 + `asyncio.to_thread` disrupts coverage's settrace hook

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

## Post-deploy Checklist

### Add Vite polyfill hash to `script-src`

Vite injects a small inline `<script>` polyfill for `<link rel="modulepreload">` into the built `index.html`. The current `script-src 'self'` in `frontend/nginx.conf` will block it. After the first production build:

1. Inspect `frontend/dist/index.html` for any `<script>` blocks that have no `src` attribute (inline scripts).
2. For each one, compute its SHA-256 hash:
   ```bash
   # Copy the exact text content between <script> and </script> (no tags, no newline at end)
   printf '%s' 'INLINE_SCRIPT_CONTENT_HERE' | openssl dgst -sha256 -binary | openssl enc -base64
   ```
3. Add the resulting hash to `script-src` in `frontend/nginx.conf`:
   ```nginx
   script-src 'self' 'sha256-HASH_HERE';
   ```
4. If there is no inline script in `dist/index.html`, no change is needed — `script-src 'self'` is already correct.
