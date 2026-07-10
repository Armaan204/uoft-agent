<div align="center">

# UofT Agent

AI academic assistant for University of Toronto students.

[![Coverage](docs/coverage.svg)](https://github.com/armaan204/uoft-agent/actions)

![Demo](assets/demo.gif)

</div>

## 🚀 Live App

**[uoft-agent.com](https://uoft-agent.com/)** — create an account or sign in with Google, then connect your Quercus token to get started.

**[Try the demo](https://uoft-agent.com/demo)** — explore the full UI with sample data, no account needed.

---

## 🤔 What It Does

Stop juggling Quercus, ACORN, and a calculator at the same time. UofT Agent pulls your live course data, does the grade math for you, and gives you an AI that actually knows your marks.

**📊 Dashboard**
- All your current courses in one place with live grade breakdowns
- Upcoming deadlines and recent announcements side-by-side
- Grades load instantly even on a new device or incognito tab (3-tier cache: memory → Supabase snapshot → live Quercus fetch)
- Hit refresh any time; existing data stays visible while the update runs in the background

**📝 Per-Course Grade Detail**
- Full weighted breakdown by component (assignments, midterms, finals, etc.)
- What-if sliders — drag to see what you need on the final to hit your target grade
- Inline grade editing: override any component score directly in the UI; changes persist across devices
- Syllabus weights auto-extracted from Canvas assignment groups or, if missing, from your course syllabus PDF/DOCX/page via Claude

**🤖 AI Chat**
- Ask anything: *"What do I need on my CSCA48 final to keep an A?"*, *"How are my grades across all courses?"*, *"Any announcements I missed this week?"*
- Threaded conversations with full history — pick up where you left off
- Claude uses deterministic tool calls for grade math; it never guesses your percentages
- Announcement detail loads in-app — no jumping to Quercus

**🎓 ACORN Import**
- Download your Complete Academic History PDF from ACORN and upload it — done
- Sessional and cumulative GPA over time with an interactive chart
- Sortable course table with every grade you've ever gotten at UofT
- Total earned credits (IPR and NGA excluded so the number actually makes sense)
- Transfer credits and CR/NCR courses handled correctly

**🗺️ Degree Planner** *(UTSC)*
- Paste your program name → the app finds your calendar page, extracts requirements with Claude, and matches them against your ACORN history
- Handles required courses, credit-from-list requirements, and open-pool department/level filters
- Co-op programs: work term requirements tracked separately from academic requirements
- No double-counting — each course satisfies at most one requirement slot

---

## ⚡ How It Works

1. Create an account with email/password, or sign in with Google
2. Paste your Quercus personal access token (Settings → Profile → Approved Integrations)
3. The app encrypts it and stores it in Supabase so you never have to paste it again
4. Dashboard loads automatically — grades, deadlines, announcements
5. Download your Complete Academic History PDF from ACORN and upload it for GPA tracking + Degree Planner
6. Chat with the AI about anything academic

---

## 🏗️ Architecture

```
frontend/          Vite + React  →  uoft-agent.com
api/               FastAPI       →  email/password auth, Google OAuth, grades, chat, ACORN, graduation
agent/             Anthropic tool-calling loop (no LangChain)
calculator/        Deterministic grade engine + UofT GPA mapping
integrations/      Quercus client, syllabus parser, graduation service, ACORN store
auth/              Supabase-backed user + encrypted token persistence
uoft-acorn-extension/   Manifest V3 Chrome extension (published on Web Store)
```

Key FastAPI routes:

| Method | Route | What it does |
|--------|-------|-------------|
| `POST` | `/auth/signup` | Create an email/password account |
| `POST` | `/auth/login` | Sign in with email/password |
| `GET` | `/auth/google` | Start Google OAuth |
| `GET` | `/auth/me` | Current user info |
| `GET` | `/api/courses/dashboard` | Courses + deadlines + announcements |
| `GET` | `/api/courses/{id}/grades` | Full grade breakdown |
| `POST` | `/api/courses/{id}/grade-overrides` | Save a score override |
| `GET` | `/api/courses/{id}/scenarios` | What-if target grade scenarios |
| `POST` | `/api/chat` | Run AI agent, persist exchange |
| `GET` | `/api/chat/history` | All past conversations |
| `GET` | `/api/graduation/progress` | Degree planner analysis |

---

## 🔒 Security

UofT Agent handles sensitive academic data — Quercus API tokens, transcripts, grades, and GPAs. The app underwent a comprehensive security hardening pass before public launch:

- **Authentication hardening** — JWTs include `iss`, `aud`, `iat`, `jti` claims with validation; 1-day expiry; `python-jose` replaced with actively maintained `PyJWT`
- **OAuth CSRF protection** — Google OAuth uses a cryptographic `state` parameter stored in an HMAC-signed HttpOnly cookie
- **Rate limiting** — Auth endpoints rate-limited (5/min login, 3/min signup/reset); chat rate-limited per user (10/min, 50/day)
- **Quercus token security** — Tokens sent via `X-Quercus-Token` header (never in URLs); encrypted with Fernet at rest; never returned in plaintext API responses
- **XSS defense-in-depth** — DOMPurify on the frontend + `nh3` allowlist sanitizer on the backend for announcement HTML
- **Security headers** — CSP, HSTS with preload, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`
- **Error sanitization** — All API error responses use generic messages; internal details logged server-side only
- **Account deletion** — Full cascade delete across all 11 data tables via `DELETE /auth/account` and in-app UI
- **CORS** — Restricted to explicit methods and headers; no wildcards with credentials
- **Admin isolation** — Admin router only loads when `ENVIRONMENT == "development"` (explicit allowlist)
- **Dependency hygiene** — All production dependencies pinned to exact versions

See the [Privacy Policy](https://uoft-agent.com/privacy) and [Terms of Use](https://uoft-agent.com/terms) for data handling details.

---

## 🛠️ Local Development

```bash
# Python backend
pip install -r requirements.txt

# Create .env
ANTHROPIC_API_KEY=...
SUPABASE_URL=...
SUPABASE_KEY=...
SUPABASE_ANON_KEY=...
ENCRYPTION_KEY=...
JWT_SECRET=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
REDIRECT_URI=http://localhost:8001/auth/callback
FRONTEND_URL=http://localhost:5173
PASSWORD_RESET_REDIRECT_URL=http://localhost:5173/auth/reset-password

# Run FastAPI
uvicorn api.main:app --reload --port 8001
# Swagger UI → http://localhost:8001/docs

# Run React frontend
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

## 🧪 Tests

```bash
python -m coverage run -m pytest tests/ -q
python -m coverage report
```

813 tests, 100% coverage.

---

## ⚠️ Current Limitations

- Some courses show no weighted overview grade when the syllabus-to-assignment mapping is too ambiguous to trust
- Quercus-posted grade changes can take a few minutes to appear due to short-lived caching
- Degree Planner currently supports UTSC calendar pages only (UTM and St. George coming later)

---

## 💬 Support

Found a bug or have a feature request? [Open an issue](https://github.com/armaan204/uoft-agent/issues) or email uoftagent@gmail.com.

## 📄 License

MIT. See [`LICENSE`](LICENSE).
