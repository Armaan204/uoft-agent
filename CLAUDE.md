# uoft-agent

An AI agent for University of Toronto students. Uses tool-calling
(Claude API function calling) to answer academic questions in natural
language.

## What it does

- Fetches live data from Quercus (Canvas API) and ACORN
- Extracts grade weights from unstructured syllabi
- Answers questions like "what do I need on the final to pass?"
- Imports ACORN academic history via a user-triggered Chrome extension
- Plans to support Gradescope and MarkUs in future

## Architecture

- `agent/` — agent loop, tool definitions, prompts
- `integrations/` — one file per platform (quercus, acorn, etc.)
- `calculator/` — pure Python grade math, no LLM involved
- `app.py` — Streamlit entry point
- `api_server.py` — minimal ACORN import API backed by Supabase Postgres
- `uoft-acorn-extension/` — Manifest V3 Chrome extension for ACORN import

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
SUPABASE_URL
SUPABASE_KEY
ENCRYPTION_KEY
REDIRECT_URI           # optional override for the OAuth redirect URL

## Auth

Google OAuth is handled by Supabase Auth (not directly by the app).
Configure Google as a provider in the Supabase dashboard and add the
allowed redirect URLs there. The app only needs SUPABASE_URL and
SUPABASE_KEY — no Google client credentials in the app environment.

Redirect URLs (must be added to Supabase dashboard → URL Configuration):
- Local: `http://localhost:8501`
- Production: `https://uoft-agent.streamlit.app`

Auth flow (`auth/supabase_auth.py`):
1. `get_google_login_url()` calls `supabase.auth.sign_in_with_oauth`,
   caches the URL + PKCE verifier in session state, returns the URL.
2. `st.link_button` sends the user to Supabase → Google → back to app.
3. `init_auth()` (called at top of `main()`) reads `?code=` from query
   params, calls `exchange_code_for_session`, stores the user in session
   state, and clears the query param.
4. `get_logged_in_user()` / `logout()` read/clear session state.

## Current status

Core pipeline working end-to-end. Streamlit UI running locally.

**Done:**
- Quercus integration complete — courses, assignments, submissions,
  assignment groups, syllabus body, files, and grade enrollment
- Course list filtered dynamically to the current dated term using
  Canvas term `start_at` / `end_at` metadata, with resource pages
  excluded and sensible fallback to nearest upcoming / most recent term
- Grade weight resolution: Canvas `group_weight` used directly when
  non-zero (preferred, no LLM needed); falls back to three-stage
  syllabus parsing — `syllabus_body` PDF → modules/files search →
  front page links
- Fuzzy keyword matching in `_match_weight()` handles mismatches
  between Canvas group names and syllabus weight labels (e.g.
  "MIDTERM TEST" ↔ "Mid-term Examination")
- Weighted-component resolution now also matches syllabus item names to
  Canvas assignment names inside broad groups (e.g. MUZA99
  "Assignments" / "Tests"), so item-level syllabus weights can still
  drive weighted grade calculations and projections
- Grade calculator verified correct for EESA10, STAD68, and MUZA99 —
  current grade, needed score on final, and letter-grade scenarios
- Agent loop with native Claude API function calling (no LangChain)
- Streamlit chat UI with tool-call expanders (`streamlit run app.py`)

- Token onboarding screen in Streamlit — token validated via `get_courses()`
  on connect, stored in session state only (never written to disk)
- Token threaded from session state → `run()` → `execute_tool()` →
  `QuercusClient(token=...)` — no hardcoded env dependency in the UI
- Anthropic key resolution supports both local `.env` and Streamlit
  Cloud `st.secrets` without breaking the CLI path
- Public privacy-policy route available in Streamlit via
  `?page=privacy` for Chrome Web Store submission

- Streamlit dashboard (loads before chat) with per-course summary cards:
  - Parallel data loading via `concurrent.futures.ThreadPoolExecutor`
  - Grade display uses accumulated grade: earned pts + full credit on
    ungraded work (i.e. "start at 100%, subtract marks lost so far")
  - Progress bar and risk flag (Safe ≥85%, On track 70–84%, At risk <70%)
  - Overview grade shown only when the weighted component model is
    reliable enough to support the dedicated breakdown page; courses
    with unresolved weights are left blank rather than falling back to
    raw total points
  - Single "Grade breakdown" button on eligible cards opens a dedicated
    per-course breakdown page instead of duplicating the same logic in
    an inline expander
  - Upcoming deadlines (next 14 days) across all courses, sorted by date
  - Recent announcements section added, showing the latest announcement
    per course with direct Quercus links
  - Refresh button clears session cache and reloads

- Dedicated per-course breakdown / what-if page for reliably weighted
  courses:
  - Shows weighted components already completed, with contribution in pts
  - Separates Marked Components and Remaining Components
  - Marked components can be overridden with sliders when Quercus
    mapping is slightly off; remaining components still default to 100
  - Recomputes projected final grade live as the sliders move, while
    current standing stays system-derived
  - Enabled only when the weighted component mapping is reliable; mixed
    partial-group cases are blocked rather than approximated

- Syllabus retrieval / weighting accuracy improved:
  - Module file discovery now resolves Canvas file metadata before
    filtering on extension, so module items titled generically
    ("Course outline") still lead to the underlying PDF
  - Weighted-component matching can split broad Canvas groups into
    item-level syllabus components when assignment names support it
    (e.g. proposal items inside a broader final-project group)
  - Repeated assignments can accumulate into one syllabus component
    instead of being treated as separate unmatched items
  - Future-only syllabus weights such as a not-yet-posted final exam
    are carried as ungraded components instead of making the course
    ineligible immediately
  - STAD68H3 and STAC51H3 are now handled correctly by the course
    overview / breakdown flow after these fixes

- ACORN import flow implemented end-to-end:
  - Chrome extension (`uoft-acorn-extension/`) runs only on
    `acorn.utoronto.ca`, does not handle login / credentials, and
    extracts academic history only after the user clicks the popup button
  - ACORN parsing rewritten for the real DOM shape — transcript data
    extracted from `div.courses` plain-text blocks rather than tables
  - Popup → background → content-script message passing implemented
    cleanly, with backend POST handled in the service worker
  - Browser extension posts parsed ACORN history to
    `POST /api/acorn/import`
  - Minimal backend (`api_server.py`) stores imports in Supabase
    Postgres, keyed by import code
  - `GET /api/acorn/latest?import_code=...` and
    `GET /api/acorn/status?import_code=...` implemented for readback
  - Per-user import code flow added so each Streamlit session reads only
    the ACORN payload associated with its own code
  - Streamlit ACORN tab added:
    - Explains the extension workflow
    - Displays the import code to paste into the extension
    - Refreshes by reading ACORN data back from the deployed backend
    - Shows imported course count, timestamp, and a simple course table
  - Backend prepared for deployment and deployed publicly (Railway);
    Streamlit ACORN reads and extension writes now target the hosted
    backend rather than localhost
  - Backend no longer depends on local disk JSON storage; `.env`
    loading and Supabase error handling were tightened for local and
    deployed debugging
  - Extension prepared for Chrome Web Store submission:
    - placeholder icons added
    - raw academic-history console logging disabled by default
    - privacy-policy files added
    - popup copy made explicit about not collecting passwords
    - unused `scripting` permission removed from the manifest

- GitHub Pages landing site added under `docs/` for Chrome Web Store /
  verification needs:
  - `docs/index.html` landing page
  - `docs/privacy.html` privacy policy page
  - Google verification file support and `.nojekyll`

- Google OAuth login gate implemented via Supabase Auth (`auth/supabase_auth.py`):
  - Supabase owns the OAuth redirect; the app generates a link_button URL
    and processes the ?code= callback via exchange_code_for_session (PKCE)
  - No streamlit-google-auth dependency; no cookie management in the app
  - Works correctly with Streamlit's rerun model on Cloud

**Known gap:**
- `get_grade_scenarios` bug fixed: groups with no assignments posted yet
  (e.g. FINAL EXAM before the assignment is created) are now correctly
  treated as ungraded rather than skipped
- What-if sliders currently require a fully reliable weighted component
  model; courses with partial group-level weights are intentionally
  blocked rather than estimated heuristically
- ACORN backend currently uses import-code scoping instead of a full
  auth / account system — simple and sufficient for now, but not a
  long-term replacement for proper user identity if the project grows
- Auth is now Supabase Auth (PKCE flow); session persists in Streamlit
  session state only (no server-side cookies or token storage)

**Not yet started:**
- Gradescope and MarkUs integrations
