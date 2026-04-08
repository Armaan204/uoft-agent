<div align="center">

# UofT Agent

🎓🤖 An **AI agent for University of Toronto students** that uses live academic data, tool calling, and agentic workflows to answer course and grade questions in natural language.

</div>

## 🚀 Live Streamlit Demo

**Try it here:** https://uoft-agent.streamlit.app/

This project is built around a live **Streamlit demo** that exposes the agent through a clean student-facing interface.

With a Quercus token, the agent can:

- inspect live course data
- retrieve assignments and submissions
- resolve grading weights from Canvas or the syllabus
- compute current standing with deterministic Python logic
- reason about grade outcomes and required scores
- answer academic questions through a multi-step tool-using workflow

## ✨ Why It’s Interesting

This is not just a chatbot wrapper.

UofT Agent is an **agentic academic assistant**: a tool-using LLM system that decides when to gather structured data, when to call grading utilities, and when to return a final answer. Instead of relying on the model to guess numbers, the system pushes real computation into Python and uses the model for orchestration and reasoning.

That means the workflow is:

1. Understand the student's question
2. Decide which tools to call
3. Pull live data from Quercus
4. Resolve grading weights from Canvas or syllabus files
5. Run deterministic grade calculations
6. Feed the tool results back into the agent loop
7. Return a grounded natural-language answer

This is exactly the kind of **agent + tools + reasoning loop** that makes LLM systems feel substantially more capable than a static prompt-response app.

## 🧠 Agentic Workflow

The core agent loop lives in [`agent/agent.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/agent/agent.py).

The system uses native Anthropic tool calling to support workflows such as:

- `get_courses`
- `get_course_weights`
- `get_current_grade`
- `get_grade_scenarios`

The model can chain these tools together as needed. For example:

- If a student asks about a course by name, the agent can first resolve the course from the course list
- If weights are missing from Canvas, the workflow can pivot to syllabus parsing
- If the student asks what they need on the final, the agent can fetch current grade data and then run the scenario calculator

This gives the app a clear **agentic execution path** rather than a single-shot completion.

## 💬 Streamlit Demo Experience

The Streamlit app in [`app.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/app.py) is the main demo surface.

It showcases:

- 🔐 token-based onboarding for Quercus access
- 📚 live course overview cards
- 📈 weighted grade breakdowns
- ⚠️ course-level academic risk signals
- 📅 upcoming deadline aggregation
- 💬 natural-language interaction with the AI agent
- 🛠️ visible tool-call traces for demos, debugging, and transparency

So the product is not only an agent under the hood, but also a compelling **interactive demo of agentic workflows in action**.

## 🏗️ Architecture

The repo is intentionally modular:

- [`app.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/app.py) - Streamlit UI and dashboard
- [`agent/agent.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/agent/agent.py) - main AI agent loop
- [`agent/tools.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/agent/tools.py) - tool schemas and dispatch layer
- [`integrations/quercus.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/integrations/quercus.py) - Quercus / Canvas integration
- [`integrations/syllabus.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/integrations/syllabus.py) - syllabus discovery and parsing workflow
- [`calculator/grades.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/calculator/grades.py) - deterministic grade engine

Core design choices:

- **No LangChain**: native tool calling only
- **LLM for reasoning, Python for arithmetic**
- **Live data retrieval before final answers**
- **Syllabus parsing as a fallback workflow when APIs are incomplete**

## 📊 Grading Intelligence

The dashboard and agent both use the same grading pipeline:

1. Try Canvas assignment-group weights
2. If unavailable, discover the syllabus PDF
3. Extract grading components from the syllabus
4. Match syllabus components against Canvas structure
5. Compute weighted standing and future-grade scenarios

This is especially important because many real courses do not expose clean grading metadata through the LMS. The system therefore behaves like a practical agent: it adapts, searches for alternate evidence, and continues the workflow instead of failing immediately.

## 🛠️ Run Locally

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Add a local `.env`

```env
ANTHROPIC_API_KEY=your_anthropic_key
QUERCUS_API_TOKEN=your_quercus_token
```

Optional placeholders for future integrations:

```env
ACORN_USERNAME=your_utorid
ACORN_PASSWORD=your_password
```

### 3. Start the Streamlit demo

```bash
streamlit run app.py
```

## ☁️ Streamlit Cloud

The app supports **Streamlit Cloud** deployment using `st.secrets` for the Anthropic key.

Set:

```toml
ANTHROPIC_API_KEY = "your_anthropic_key"
```

Students enter their own Quercus token through the app UI, which keeps the deployed demo flexible and user-specific.

## 🚂 Backend Deployment

The ACORN import backend is intentionally small and can be deployed separately from Streamlit.

Recommended setup:

- **Streamlit app** on Streamlit Cloud
- **ACORN backend** on Railway

The backend entry point is [`api_server.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/api_server.py), and it supports:

- `POST /api/acorn/import`
- `GET /api/acorn/latest?import_code=...`
- `GET /api/acorn/status?import_code=...`

The backend now stores ACORN imports in **Supabase Postgres** rather than
disk-backed JSON files. Railway hosts the API, while Supabase stores the
imported payloads.

### Local backend

```bash
python api_server.py
```

### Deploying on Railway

This repo now includes a minimal [`Procfile`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/Procfile):

```text
web: python api_server.py
```

The backend reads:

- `HOST` (defaults to `0.0.0.0`)
- `PORT` (defaults to `8000`)
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `ENCRYPTION_KEY`

On Railway, `PORT` is injected automatically, so the same backend can run locally and in production without code changes.

On Railway, `PORT` is injected automatically, so the same backend can run
locally and in production without code changes. The Supabase credentials and
Fernet key should be configured as Railway environment variables.

## ✅ Current Agent Capabilities

- Live Quercus course retrieval
- Assignment and submission retrieval
- Canvas weight resolution
- Syllabus PDF discovery across multiple course surfaces
- Syllabus-based grading extraction with Claude
- Deterministic current-grade computation
- Letter-grade scenario analysis
- Streamlit-based interactive AI agent demo

## 🔜 Next Agent Workflows

- ACORN integration for transcript and GPA workflows
- Gradescope integration
- MarkUs integration
- broader academic planning workflows
- stronger automated evaluation and testing

## 📄 License

MIT. See [`LICENSE`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/LICENSE).
