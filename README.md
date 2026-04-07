# UofT Agent

A Streamlit-based academic assistant for University of Toronto students.

The app connects to Quercus, reads live course data, extracts grading weights from the syllabus when needed, and answers natural-language questions such as:

- What is my current standing in this course?
- What do I need on the final to get an A-?
- Which assignments are due in the next two weeks?

The project is designed as a lightweight demo application: Streamlit handles the UI, Anthropic handles reasoning and tool selection, and Python handles all grade calculations.

## Streamlit Demo

The main product surface is the Streamlit app in [`app.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/app.py).

The demo includes:

- A Quercus token onboarding flow
- A course overview dashboard
- Per-course grade cards with weighted breakdowns
- Upcoming deadlines across courses
- A chat interface for grade and course questions
- Tool-call visibility for debugging and demos

### Dashboard behavior

For each course, the dashboard tries to compute a meaningful current standing using the best available source:

1. Canvas assignment-group weights, if the course exposes them
2. Syllabus-derived weights, extracted from the course syllabus PDF
3. No overview grade if neither source is available

This keeps the dashboard conservative: it only shows a weighted overview when the app can actually justify it.

## Demo Architecture

The project is intentionally simple:

- [`app.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/app.py): Streamlit UI and dashboard
- [`agent/agent.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/agent/agent.py): Claude tool-calling loop
- [`agent/tools.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/agent/tools.py): tool schemas and dispatch
- [`integrations/quercus.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/integrations/quercus.py): Quercus/Canvas API client
- [`integrations/syllabus.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/integrations/syllabus.py): syllabus discovery and weight extraction
- [`calculator/grades.py`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/calculator/grades.py): pure grade math

Key design choices:

- No LangChain or framework-heavy orchestration
- Native Anthropic tool calling only
- Grade arithmetic stays in Python, not in the LLM
- Syllabus parsing is only used when Canvas does not expose weights directly

## Running Locally

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set environment variables

Create a local `.env` file:

```env
ANTHROPIC_API_KEY=your_anthropic_key
QUERCUS_API_TOKEN=your_quercus_token
```

Optional placeholders for future integrations:

```env
ACORN_USERNAME=your_utorid
ACORN_PASSWORD=your_password
```

### 3. Launch the Streamlit demo

```bash
streamlit run app.py
```

Then open the local Streamlit URL in your browser.

## Deploying on Streamlit Cloud

This project supports Streamlit Cloud secrets for the Anthropic API key.

Set the following in your Streamlit Cloud app secrets:

```toml
ANTHROPIC_API_KEY = "your_anthropic_key"
```

Quercus access is handled in the app UI through the student's personal access token, so the Streamlit demo does not need a shared Quercus token baked into deployment.

## How It Works

When the user opens the app:

1. They enter a Quercus personal access token
2. The app validates the token against Quercus
3. The dashboard loads current courses in parallel
4. For each course, the app fetches assignments, submissions, and weights
5. If Canvas weights are unavailable, the app attempts to find and parse the syllabus
6. The chat interface uses Anthropic tool calling to answer questions using the same live data

## Current Capabilities

Implemented today:

- Quercus course listing
- Assignment and submission retrieval
- Assignment-group weight support from Canvas
- Syllabus PDF discovery from course pages, files, and modules
- Syllabus weight extraction with Claude
- Grade breakdowns and letter-grade scenarios
- Streamlit chat and dashboard demo

Planned or partial:

- ACORN integration
- Gradescope integration
- MarkUs integration
- More formal automated test coverage

## Notes and Limitations

- The app currently filters Quercus courses to the 2026 term logic implemented in the client.
- Syllabus extraction depends on the syllabus being accessible through Quercus and readable as text.
- Some courses use coarse Canvas groups and fine-grained syllabus labels; the calculator now attempts to reconcile those by matching assignment names inside groups.
- The included `test_*.py` files are live-data scripts rather than a full unit test suite.

## Repository Status

This repository is best understood as a polished demo and working prototype rather than a finished production system. The Streamlit app is the main deliverable and the clearest way to evaluate the project.

## License

MIT. See [`LICENSE`](/C:/Users/armaa/OneDrive/Documents/Armaan/UofT/uoft-agent/LICENSE).
