# uoft-agent

An AI academic assistant for University of Toronto students.

## Live URLs

- Main app: `https://uoft-agent.com`
- Chrome extension (deprecated — replaced by PDF upload): `https://chromewebstore.google.com/detail/akchfgkjeenfkmcommdpnimgkbnclgfa?utm_source=item-share-cb`

## What It Does

- Connects to Quercus with a student-provided personal access token
- Persists the Quercus token per logged-in user in Supabase after encrypting it with Fernet
- Computes current standing and target-grade scenarios with deterministic Python math
- Resolves course weights from Canvas assignment groups when available
- Falls back to syllabus discovery and Anthropic-based weight extraction when Canvas weights are missing
- Supports syllabi published as PDFs, DOCX files, or Canvas pages
- Imports ACORN academic history via PDF upload (students download their Complete Academic History PDF from ACORN and upload it directly)
- The ACORN Chrome extension is deprecated; PDF upload is now the primary import method

## Architecture

- `uoft-acorn-extension/` — Manifest V3 Chrome extension for ACORN import (deprecated — replaced by PDF upload)
- `api/` — entire Python backend powering the deployed app at `https://uoft-agent.com`
  - `api/main.py` — FastAPI app with CORS, mounts all routers, health check at `GET /`
  - `api/dependencies.py` — JWT-based `get_current_user` dependency
  - `api/routers/auth.py` — email/password auth, Google OAuth flow with CSRF state, JWT issuance (1-day expiry), rate-limited auth endpoints, `/auth/me`, `/auth/logout`, `DELETE /auth/account`
  - `api/routers/courses.py` — course, grade, scenario, weight routes + Quercus token CRUD
  - `api/routers/chat.py` — `POST /api/chat` runs agent via `run_in_executor`, persists exchanges by `conversation_id`, and exposes chat-history list/detail/delete routes
  - `api/routers/acorn.py` — ACORN routes: PDF upload (`POST /upload`), authenticated claim, and data retrieval
  - `api/routers/graduation.py` — `GET /api/graduation/progress` and `DELETE /api/graduation/cache`
  - `api/routers/manual_courses.py` — CRUD for manually added courses and deadlines, plus syllabus upload endpoint
  - `api/services/course_service.py` — uncached Quercus + calculator wrappers
  - `api/services/manual_course_service.py` — Supabase-backed CRUD for `manual_courses` and `manual_deadlines` tables
  - `api/services/grade_snapshot_cache.py` — 5-minute in-memory per-user cache for aggregate semester grade snapshots used by chat tools
  - `api/services/grades_snapshot_service.py` — Supabase-backed persistence layer for dashboard and course detail snapshots; `grades_snapshot` table stores `dashboard_data`, `announcements`, and `course_detail_data` JSONB columns per `(user_id, course_id)` row
  - `api/services/acorn_service.py` — ACORN business logic for the FastAPI router
  - `api/services/auth_service.py` — email/password signup/login, Google OAuth helpers, password reset, JWT signing, and cross-provider guardrails
  - `api/agent/` — Anthropic tool-calling loop, tool schemas, prompt
  - `api/auth/user_store.py` — Supabase-backed user lookup and encrypted Quercus token persistence
  - `api/calculator/` — deterministic grade calculations and weighted-component modeling
  - `api/integrations/quercus.py` — Canvas / Quercus API client
  - `api/integrations/syllabus.py` — syllabus discovery, PDF parsing, and weight extraction
  - `api/integrations/syllabus_cache.py` — persistent Supabase cache for parsed syllabus weights
  - `api/limiter.py` — slowapi rate limiter with JWT-based per-user key extraction; custom `limit()` wrapper for test compatibility
  - `api/integrations/acorn_store.py` — ACORN import payload validation and file storage
  - `api/integrations/acorn_pdf_parser.py` — deterministic regex-based parser for ACORN Complete Academic History PDFs
  - `api/integrations/grades_cache.py` — Supabase-backed grade override and saved-grade persistence
  - `api/integrations/graduation_service.py` — graduation planning service: URL discovery, LLM-based requirements extraction, and course matching
- `frontend/` — Vite + React frontend deployed at `https://uoft-agent.com`
  - `frontend/src/App.jsx` — app routes, protected shell, frontend auth callback handling
  - `frontend/src/api/client.js` — Axios client with JWT injection and 401 handling
- `frontend/src/hooks/useAuth.jsx` — localStorage-backed auth state and login completion
- `frontend/src/hooks/useQuercusStatus.jsx` — checks whether the logged-in user has a saved Quercus token
- `frontend/src/components/` — reusable UI pieces including sidebar shell, profile menu, cards, lists, and tool-call rendering
- `frontend/src/pages/` — Login, Quercus onboarding, Dashboard, Course Detail, Chat, ACORN, and Degree Planner pages
- `frontend/src/pages/demo/` — read-only demo versions of all main pages (Dashboard, Course Detail, Chat, ACORN, Degree Planner)
- `frontend/src/data/mockData.js` — static mock data powering the demo (courses, grades, announcements, ACORN, degree planner, chat responses)
- `frontend/src/context/DemoDataContext.jsx` — React context providing mock data to demo pages
- `frontend/src/components/DemoShell.jsx` — demo app shell with sidebar nav, persistent demo banner, and sign-in CTA
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
- Quercus tokens are sent via the `X-Quercus-Token` HTTP header (never in URL query params); routes fall back to the Supabase-stored token if the header is omitted
- Dashboard and course grade data use a 3-tier cache: (1) per-user in-memory Python dict (instant, lost on restart), (2) Supabase `grades_snapshot` JSONB snapshot (fast, survives restarts), (3) live Quercus fetch (slow, only on first load or force refresh). Each tier fires a background refresh to keep the next load fast.
- On every authenticated app load, `App.jsx` fires a background `GET /api/courses/dashboard` and staggered per-course `GET /api/courses/{id}/grades` requests to keep the Supabase snapshot current, so incognito and new-device loads hit Layer 2 instead of Layer 3
- The frontend uses `PersistQueryClientProvider` with a localStorage persister (24h `gcTime` and `maxAge`) so TanStack Query cache survives tab refreshes and browser restarts
- Manual dashboard refresh fetches directly and calls `setQueryData` on completion so existing data (including announcements) stays visible the entire time the refresh is in flight
- Grade overrides immediately update both the in-memory cache and Supabase snapshot so overridden grades are reflected on all subsequent cache hits
- `api/services/course_service.py` subclasses `QuercusClient` as `UncachedQuercusClient` to bypass any caching decorators on the base client methods
- JWT secret stored in `JWT_SECRET` env var; Google OAuth credentials reuse `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
- Auth uses HttpOnly cookies: short-lived access tokens (15 min) + long-lived refresh tokens (7 days); the frontend never touches JWTs directly
- Access token cookie: `HttpOnly; SameSite=Lax; Secure` (Secure only in production), `Path=/`; refresh token cookie: same flags, `Path=/auth/refresh`
- `POST /auth/refresh` rotates the access token using the refresh token cookie (rate-limited at 10/min); the frontend Axios interceptor automatically retries 401s via this endpoint
- The 401 interceptor exempts `/auth/*` URLs from refresh retry **except** `/auth/me`, which is the bootstrap call that must trigger refresh for returning users with expired access tokens
- `get_current_user` reads the `access_token` cookie first, falling back to `Authorization: Bearer` for Swagger UI
- Google OAuth callback sets auth cookies and redirects to `FRONTEND_URL/`; password login sets auth cookies in the response — no tokens in URL params or JSON body; on bootstrap, `useAuth` detects user-switches via `sessionStorage` and clears stale React Query cache to prevent data leakage on shared devices
- Production nginx proxies `/api/` and `/auth/` to the backend via `BACKEND_URL` env var (envsubst at container start), making everything same-origin
- Local dev uses Vite's built-in proxy for the same effect
- The React chat page now keeps the active in-progress conversation and unsent draft in browser `sessionStorage`, keyed per logged-in user and conversation ID, so refreshes within the tab keep the live thread without persisting it across browser restarts
- Swagger UI still supports `Authorization: Bearer` for developers pasting JWTs directly
- Production frontend is served at `https://uoft-agent.com`; backend CORS allows `FRONTEND_URL` and optional `CORS_ORIGINS`
- Graduation planning for UTSC programs uses a local PDF-first pipeline: (1) look up the program in the bundled `api/data/UTSC_Calendar_2025-2026.pdf` via a static TOC page index and heading-based text extraction, (2) pass the extracted text to the LLM for structured requirements extraction, (3) greedy matching of ACORN courses against requirements with no double-counting within the program. If the PDF lookup fails, falls back to web-based URL discovery (UTSC slug probing + Anthropic web_search + DuckDuckGo) and web page extraction.
- The PDF TOC index (`_PDF_TOC` in `graduation_service.py`) maps department names to page ranges; `_program_to_toc_section` fuzzy-matches ACORN program names to TOC sections using keyword overlap with substring containment; `_find_program_text_in_section` locates the specific program heading within the section text, scoring by keyword overlap plus program type (specialist/major/minor) and co-op status
- For co-op programs, PDF extraction pulls text from both the base department section (academic requirements) and the "Arts and Science Co-op" section (co-op course requirements), concatenating them for the LLM. The web fallback derives the base specialist page by stripping `co-operative-` from the URL slug and probing variants.
- Requirements are cached per `acorn_name` in the `program_requirements_cache` Supabase table; the Degree Planner page never auto-refetches (all TanStack Query auto-refetch options disabled) to avoid burning API credits
- Three requirement types: `required` (OR alternatives), `n_credits_from_list` (earn N credits from a list), `open_pool` (earn N credits from courses matching department+level filters, with optional sub-requirements)
- Co-op status is tracked as satisfied/in_progress/remaining; course matching is greedy with most-constrained requirements first
- The `/demo` route is fully client-side with no backend dependency; mock data uses dynamic dates (`inDays(n)` relative to today) so deadlines never appear stale; demo pages reuse presentational components but never import hooks that call the API

## Auth

The app uses FastAPI auth routes with app-issued JWT sessions. Two auth providers: email/password (via Supabase Auth) and Google OAuth.

- **Sign-in page** at `/signin` — unified page with Google OAuth button, email/password login/signup tabs, and forgot-password flow
- Email/password signup hits `POST /auth/signup`; Supabase Auth sends a verification email via Resend SMTP (custom SMTP configured in Supabase to bypass the free-tier 3 emails/hour limit)
- Verification emails redirect to `/signin?confirmed=true`, which shows a green confirmation banner
- Email/password login hits `POST /auth/login`; FastAPI validates with Supabase Auth, checks email is confirmed, links/creates the app `users` row, and sets HttpOnly auth cookies
- Password reset: `POST /auth/password/forgot` sends a Supabase reset email; `POST /auth/password/reset` applies the new password using the Supabase session tokens from the reset link
- Password reset page at `/auth/reset-password` parses the Supabase `access_token` and `refresh_token` from the URL fragment
- Google login starts at `GET /auth/google`; the callback sets HttpOnly auth cookies and redirects to `${FRONTEND_URL}/`
- Auth state is determined by calling `GET /auth/me` on app load (no client-side token storage); the Axios interceptor silently refreshes expired access tokens via `POST /auth/refresh`
- After auth, React checks for a saved Quercus token; users without one are sent to `/onboarding`
- **Cross-provider guardrails**: if a Google-only user tries to sign up with email/password, the signup is blocked with a message to use Google instead; if a Google-only user requests a password reset, the endpoint silently returns success without sending an email (anti-enumeration)
- The Axios 401 interceptor excludes `/auth/*` endpoints so failed login attempts don't redirect away from the sign-in page
- Password validation requires 8–128 characters with at least one letter and one number

## Security

The app underwent a comprehensive security hardening pass before public launch. Key measures:

### Authentication & Session Management
- Short-lived access tokens (15 min) in HttpOnly/SameSite=Lax cookies eliminate XSS-based token theft; refresh tokens (7 days) in a separate HttpOnly cookie scoped to `Path=/auth/refresh`
- JWTs include `iss`, `aud`, `iat`, `jti`, and `type` claims; `iss` and `aud` are validated on decode with backward compatibility for pre-existing tokens; `type` prevents token confusion (refresh used as access)
- `python-jose` replaced with `PyJWT` (actively maintained)
- Google OAuth uses a cryptographic `state` parameter stored in an HMAC-signed, HttpOnly cookie to prevent CSRF/login-fixation attacks
- OAuth state signing requires `JWT_SECRET`; there is no dev-fallback — the app fails loudly if the secret is missing
- Auth endpoints are rate-limited via slowapi: `/auth/login` at 5/min, `/auth/signup`, `/auth/password/forgot`, `/auth/password/reset` at 3/min each, `/auth/refresh` at 10/min
- Chat endpoint has its own per-user rate limits: 10/min and 50/day
- Logout calls `POST /auth/logout` which clears auth cookies server-side, and also clears the TanStack Query localStorage cache (`REACT_QUERY_OFFLINE_CACHE`) to prevent data persistence on shared devices

### API Security
- Quercus tokens are sent via `X-Quercus-Token` HTTP header — never in URL query params (which leak to server logs, browser history, and proxies)
- `GET /api/courses/quercus-token` returns only `{"exists": true/false}` — the plaintext token is never exposed in API responses
- Legacy unauthenticated ACORN endpoints (`POST /api/acorn/import`, `GET /api/acorn/latest`, `GET /api/acorn/status`) removed entirely; only the authenticated PDF upload and claim flows remain
- Admin router guarded with `ENVIRONMENT == "development"` (explicit allowlist, not `!= "production"`)
- CORS restricted to explicit methods (`GET`, `POST`, `PUT`, `DELETE`, `OPTIONS`) and headers (`Authorization`, `Content-Type`, `X-Quercus-Token`, `sentry-trace`, `baggage`)
- Error responses sanitized: all `str(exc)` in course and chat routers replaced with generic messages + server-side `logger.exception()` to prevent internal detail leakage
- All dependencies pinned to exact versions in `requirements.txt`

### Frontend Security
- Announcement HTML sanitized with DOMPurify on the frontend (defense-in-depth) and `nh3` allowlist sanitizer on the backend
- nginx serves security headers: `Content-Security-Policy`, `Strict-Transport-Security` (HSTS with preload), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`
- CSP blocks all external scripts, inline scripts (except whitelisted hashes), and object embeds
- Secrets are never logged: JWT values, Quercus tokens, and OAuth URLs are excluded from log output

### Data Privacy
- `DELETE /auth/account` cascades through all 11 Supabase tables (chat_messages, chat_conversations, grades_snapshot, grade_overrides, grades_cache, acorn_imports, manual_deadlines, manual_courses, quercus_tokens, syllabus_weights_cache, program_requirements_cache, users)
- "Delete my account" button in the profile menu with confirmation step and error surfacing
- Quercus tokens encrypted with Fernet before storage; the encryption key is a required env var

### Rate Limiting Architecture
- The `api/limiter.py` module wraps slowapi's `Limiter` with a custom `limit()` decorator that: (1) extracts user identity from the `access_token` cookie (or `Authorization: Bearer` header as fallback) for per-user rate limiting, falling back to IP, and (2) gracefully skips rate checking when no `Request` object is available (for unit tests that call handlers directly)
- **Important**: auth routes must use the custom `limit()` function from `api.limiter`, not `limiter.limit()` directly, because the slowapi decorator breaks FastAPI's Pydantic model resolution when `from __future__ import annotations` is active (the wrapper's `__globals__` doesn't contain the route's type annotations). The `auth.py` router avoids `from __future__ import annotations` for this reason.

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
- `SUPABASE_ANON_KEY` optional explicit key for Supabase Auth client; falls back to `SUPABASE_KEY`
- `PASSWORD_RESET_REDIRECT_URL`, e.g. `http://localhost:5173/auth/reset-password`
- `JWT_SECRET` for signing FastAPI JWTs (generate: `python -c "import secrets; print(secrets.token_hex(32))"`)
- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` for FastAPI Google OAuth
- `REDIRECT_URI` for FastAPI Google OAuth callback, e.g. `http://localhost:8001/auth/callback`
- `FRONTEND_URL` for the React app callback target, e.g. `http://localhost:5173`
- `CORS_ORIGINS` optional comma-separated extra allowed frontend origins for FastAPI CORS
- `BACKEND_URL` (frontend container only) for nginx reverse proxy, e.g. `https://uoft-agent-production.up.railway.app`

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
- ACORN import via PDF upload: students download their Complete Academic History PDF from ACORN and upload it directly; deterministic regex-based parser extracts terms, courses, GPAs, and programs without LLM
- Legacy unauthenticated Chrome extension import endpoints removed; only authenticated PDF upload and claim flows remain
- The ACORN page shows either saved ACORN data or the onboarding / re-import flow
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
- Public demo mode at `/demo` — entirely client-side, no auth or backend calls; uses static mock data via `DemoDataContext`; covers Dashboard, Course Detail (with working what-if sliders), Chat (canned responses via suggestion chips), ACORN (GPA chart + course table), and Degree Planner; persistent amber banner links to sign-in; "Try the demo" button on landing page
- Email/password authentication with Supabase Auth: signup with email verification, login with confirmation check, password reset flow, and cross-provider guardrails (Google-only accounts blocked from password signup, silent no-op on password reset)
- Dedicated `/signin` page with Google OAuth, email/password login/signup tabs, forgot-password mode, and green email-verified confirmation banner
- Verification emails sent via Resend custom SMTP (configured in Supabase dashboard) to avoid the free-tier rate limit
- Manual course entry pivot (all 8 phases complete): Quercus API tokens are now fully optional. Users can add courses manually with weight entry or syllabus upload (PDF/DOCX, auto-extracted on file select). Manual courses use negative BIGINT IDs to avoid collision with Canvas IDs. Dashboard merges Quercus and manual courses with optimistic UI updates for add/delete operations. Course detail, what-if sliders, and grade overrides work identically for manual courses. Chat agent tools include manual courses with projected grades (100% default for ungraded components) and handle missing Quercus tokens gracefully. Manual deadlines can be added to any course (Quercus or manual) and deleted with confirmation. Sidebar has a dedicated Connect/Disconnect Quercus button. Non-Quercus users see an announcements CTA prompting connection. `QuercusClient` no longer falls back to `QUERCUS_API_TOKEN` env var when explicitly passed no token, preventing cross-user data leakage.
- React frontend polish and completion of remaining product flows
- Chat history polish such as rename support and any further navigation / UX refinement
- UTM and St. George program support in the Degree Planner: the graduation pipeline currently only discovers and extracts UTSC calendar pages. When adding support for UTM (`utm.calendar.utoronto.ca`) or St. George (`artsci.calendar.utoronto.ca`) programs, two changes are required:
  1. **Extraction prompt** (`integrations/graduation_service.py` → `_SCHEMA_HINT`): add an explicit instruction that `open_pool` level filters must always be expressed as UTSC letter notation (`A`/`B`/`C`/`D`) regardless of how the calendar phrases it — UTSC calendars say "C-level", but UTM/St. George calendars say "300-level". Without this instruction the LLM may extract `levels: ["3","4"]` instead of `["C","D"]`, causing all open-pool level comparisons to silently fail.
  2. **`_parse_dept_level`** already handles the student-course side: non-UTSC codes like `CSC300H1` are mapped to `('CSC', 'C')` via `_NUMERIC_LEVEL_MAP`. No change needed there.
     The extraction-side normalization (point 1) is the only remaining gap before UTM/St. George program requirements can be correctly matched against a student's courses.

## Known Constraints

- Courses with unresolved or only partially reliable syllabus-to-Canvas mappings intentionally show no weighted overview grade
- What-if sliders are only enabled when the weighted component model is reliable
- Quercus token persistence requires a valid `ENCRYPTION_KEY` and Supabase tables compatible with the app's `users` and `quercus_tokens` queries
- Persistent syllabus caching requires a `syllabus_weights_cache` table in Supabase
- Quercus grade changes can take up to about 5 minutes to appear because submissions and assignment groups are cached for 300 seconds
- Auth cookies require same-origin deployment (nginx proxy in production, Vite proxy in dev); the `BACKEND_URL` env var must be set on the frontend container for the nginx proxy to work
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
- `tests/test_acorn_service.py` — `api/services/acorn_service.py` Supabase ACORN service, `store_acorn_pdf_import`, and upload router endpoint
- `tests/test_acorn_pdf_parser.py` — `integrations/acorn_pdf_parser.py` deterministic PDF parser unit and integration tests
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

## Assessment Matching Logic

`GradeCalculator._best_assignment_weight_key` in `api/calculator/grades.py` maps Canvas assignments to syllabus weight keys. It uses a two-pass strategy:

1. **Direct match** (exact, substring, containment) against all available keys including the group's own key
2. **Fuzzy keyword match** (with group_key excluded) — but only accepted if the fuzzy match has strictly more keyword overlap than the assignment's own group_key; otherwise returns None so the assignment falls back to its group-level weight

This prevents two classes of bugs:
- **Group-key exclusion**: a group named "Quizzes" fuzzy-matches to "quiz 1" as group_key, excluding it from candidates so "Quiz 1" assignment cross-matches to "quiz 2"
- **Cross-group fuzzy bleed**: an assignment like "Reflective Paper" in group "Pre-Departure Paper" fuzzy-matches to "Reflective Journal" via the shared keyword "reflective" instead of falling back to its own group weight

When modifying this logic, always add regression tests that reproduce the matching pattern (not the specific course data). Test fixtures must use generic assessment names — never reference real course codes, instructor names, or assessment titles from actual courses.

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
