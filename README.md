<div align="center">

# UofT Agent

AI academic assistant for University of Toronto students.

![Demo](assets/demo.gif)

</div>

## Live App

https://uoft-agent.com/

## Chrome Extension

UofT Agent Connector is published on the Chrome Web Store:

https://chromewebstore.google.com/detail/akchfgkjeenfkmcommdpnimgkbnclgfa?utm_source=item-share-cb

## Overview

UofT Agent combines live Quercus data, deterministic grade math, ACORN academic-history import, and an Anthropic-powered tool-calling assistant.

Current capabilities:

- Google sign-in through the FastAPI + React app
- Encrypted Quercus-token persistence per logged-in user in Supabase
- Dashboard with current courses, grades, announcements, and upcoming deadlines
- Per-course grade breakdowns and what-if calculations
- ACORN academic-history import via the Chrome extension and backend API
- In-app chat that can answer questions using Quercus grades, academic history, and announcements

## Core Flow

1. The student signs in with Google through the deployed FastAPI + React flow.
2. On first use, the student enters a Quercus personal access token.
3. The app validates the token, encrypts it, and stores it in Supabase for that logged-in user.
4. The dashboard loads current courses, grade data, deadlines, and recent announcements from Quercus.
5. If Canvas weights are missing, the app searches for a syllabus and extracts weights with Anthropic.
6. Deterministic Python code computes grades, projected outcomes, and target-grade scenarios.
7. The chat agent uses tool calls to answer questions about current grades, academic history, and course news.

## Architecture

- [`frontend/`](C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/frontend) — Vite + React frontend deployed at `https://uoft-agent.com`
  - login, onboarding, dashboard, course detail, chat, and ACORN pages
  - TanStack Query for client-side fetching and caching
  - Markdown-style rendering for assistant responses
- [`api/`](C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/api) — FastAPI backend powering the deployed app
  - Google OAuth + JWT auth
  - Quercus token CRUD and course-grade routes
  - chat route that runs the Anthropic tool-calling agent
  - ACORN routes used by the extension and frontend
- [`agent/`](C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/agent) — Anthropic agent loop, prompt, and tool definitions
- [`calculator/`](C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/calculator) — deterministic grade engine and explicit UofT GPA mapping
- [`integrations/`](C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/integrations) — Quercus client and syllabus discovery/parsing
- [`auth/user_store.py`](C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/auth/user_store.py) — Supabase-backed user lookup and encrypted Quercus-token persistence
- [`uoft-acorn-extension/`](C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/uoft-acorn-extension) — published Chrome extension for ACORN import

## Key Product Decisions

- The LLM handles orchestration and extraction tasks; Python handles arithmetic
- Grade calculations are deterministic and use explicit UofT percentage-to-letter and letter-to-GPA mappings
- Weighted grades are shown only when the component model is reliable enough
- Multi-course chat questions prefer cached grade snapshots instead of repeated live Quercus calls
- Recent announcements can be previewed on the dashboard and opened in-app for full detail
- ACORN history is imported through the extension flow, then attached to the logged-in user in Supabase

## Auth

The primary app uses FastAPI Google OAuth plus frontend JWT auth:

1. The frontend sends the user to `GET /auth/google`
2. FastAPI redirects to Google
3. Google returns to FastAPI at `REDIRECT_URI`
4. FastAPI signs a JWT and redirects to `${FRONTEND_URL}/auth/callback?token=...`
5. The React app stores the token locally and uses it for protected API calls

After login, the app checks whether the user already has a saved Quercus token. If not, the user is sent to onboarding.

## Data and Caching

- Quercus tokens are encrypted before being stored in Supabase
- Parsed syllabus weights are cached in-process and persisted in Supabase
- Dashboard-grade snapshots are persisted in Supabase in `grades_snapshot`
- Chat tools can use:
  - cached dashboard snapshots from Supabase for fast current-grade answers
  - short-lived in-memory aggregate grade caching per user
  - live Quercus refresh when the user explicitly asks for updated grades
- ACORN academic history is stored in Supabase and exposed to the chat agent through a service layer

## Chat Tools

The agent has deterministic tools for:

- current semester grade overviews
- per-course current grades and what-if scenarios
- cached grade snapshots and explicit grade refresh
- academic-history lookup from imported ACORN data
- recent course announcements and full announcement detail

This reduces hallucination on numeric questions and keeps multi-course responses fast.

## Local Development

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Create a local `.env`:

```env
ANTHROPIC_API_KEY=your_anthropic_key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_service_role_key
ENCRYPTION_KEY=your_fernet_key
JWT_SECRET=your_jwt_secret
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
REDIRECT_URI=http://localhost:8001/auth/callback
FRONTEND_URL=http://localhost:5173
```

Run the FastAPI backend:

```bash
uvicorn api.main:app --reload --port 8001
```

Swagger UI is available at `http://localhost:8001/docs`.

Run the React frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend is available at `http://localhost:5173`.

If you are testing the standalone ACORN import backend directly, you can also run:

```bash
python api_server.py
```

## Deployment

Current production shape:

- React frontend served at `https://uoft-agent.com`
- FastAPI backend serving auth, courses, chat, and ACORN routes
- Supabase Postgres for users, encrypted Quercus tokens, syllabus cache, ACORN imports, and grade snapshots
- Chrome extension for ACORN academic-history import

Key backend routes include:

- `GET /auth/google`
- `GET /auth/callback`
- `GET /auth/me`
- `GET /api/courses/dashboard`
- `GET /api/courses/{course_id}/grades`
- `POST /api/chat`
- `GET /api/acorn/*`

## Legacy Streamlit App

[`app.py`](C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/app.py) is now legacy and is being phased out. The primary maintained product is the React + FastAPI app.

Keep Streamlit only if you need to reference or migrate behavior from the older UI.

## Current Limitations

- Gradescope and MarkUs integrations are still not implemented
- Some courses intentionally show no weighted overview grade when syllabus-to-assignment mapping is too ambiguous
- ACORN data supports history, GPA, and course readback, but not full graduation-audit logic
- Quercus-posted grade changes can take a few minutes to appear because of short-lived caching
- The frontend currently stores the auth JWT in localStorage; this works, but it is not the final hardened auth posture

## Support

Found a bug or have a question? Email armaanrehmanshah1@gmail.com
or [open an issue](https://github.com/armaan204/uoft-agent/issues).

## License

MIT. See [`LICENSE`](C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/LICENSE).
