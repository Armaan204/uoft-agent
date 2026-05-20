"""
tests/conftest.py — shared fixtures for uoft-agent test suite.

Environment variables are set before any application imports so that
modules that read from os.environ at import time see valid values.
All external I/O (Supabase, Anthropic, Quercus, Google) is mocked.
"""

import os

# ── starlette 1.0 / fastapi 0.103 compatibility ───────────────────────────────
# fastapi 0.103.2 calls starlette.routing.Router.__init__(on_startup=..., on_shutdown=...)
# but starlette 1.0.0 removed those kwargs in favour of `lifespan=`.
# Strip them out so the app can be imported in tests.
import starlette.routing as _sr
_orig_router_init = _sr.Router.__init__
def _compat_router_init(self, *args, **kwargs):
    on_startup  = list(kwargs.pop("on_startup",  None) or [])
    on_shutdown = list(kwargs.pop("on_shutdown", None) or [])
    _orig_router_init(self, *args, **kwargs)
    # fastapi 0.103 reads these attributes on APIRouter after construction
    if not hasattr(self, "on_startup"):  # pragma: no cover
        self.on_startup = on_startup  # pragma: no cover
    if not hasattr(self, "on_shutdown"):  # pragma: no cover
        self.on_shutdown = on_shutdown  # pragma: no cover
_sr.Router.__init__ = _compat_router_init

# starlette 0.27 TestClient called httpx.Client(app=transport, ...) but httpx 0.28
# renamed that parameter to transport=.
import httpx as _httpx
_orig_client_init = _httpx.Client.__init__
def _compat_client_init(self, *args, **kwargs):  # pragma: no cover
    if "app" in kwargs:
        kwargs.setdefault("transport", kwargs.pop("app"))
    _orig_client_init(self, *args, **kwargs)
_httpx.Client.__init__ = _compat_client_init
# ──────────────────────────────────────────────────────────────────────────────

# ── must happen before any app imports ────────────────────────────────────────
os.environ.setdefault("JWT_SECRET", "pytest-secret-do-not-use-in-prod")
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "fake-anthropic-key")
os.environ.setdefault("GOOGLE_CLIENT_ID", "fake-google-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "fake-google-client-secret")
os.environ.setdefault("ENCRYPTION_KEY", "fake-fernet-encryption-key-32bytes!")
os.environ.setdefault("QUERCUS_API_TOKEN", "fake-quercus-token")
# ──────────────────────────────────────────────────────────────────────────────

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


# ── raw data fixtures (no external deps) ──────────────────────────────────────

@pytest.fixture
def now_utc():  # pragma: no cover
    return datetime.now(timezone.utc)  # pragma: no cover


@pytest.fixture
def sample_assignment_groups():
    """Three groups: Midterm (40%), Final (40%), Assignments (20%)."""
    return [
        {
            "id": 10,
            "name": "Midterm",
            "group_weight": 40.0,
            "rules": {},
            "assignments": [
                {"id": 101, "name": "Midterm Exam", "points_possible": 100},
            ],
        },
        {
            "id": 20,
            "name": "Final",
            "group_weight": 40.0,
            "rules": {},
            "assignments": [
                {"id": 201, "name": "Final Exam", "points_possible": 100},
            ],
        },
        {
            "id": 30,
            "name": "Assignments",
            "group_weight": 20.0,
            "rules": {},
            "assignments": [
                {"id": 301, "name": "Assignment 1", "points_possible": 50},
                {"id": 302, "name": "Assignment 2", "points_possible": 50},
            ],
        },
    ]


@pytest.fixture
def sample_submissions():
    """Midterm graded at 78%, A1 at 90%, A2 at 80%. Final not yet graded."""
    return [
        {"assignment_id": 101, "score": 78.0},
        {"assignment_id": 301, "score": 45.0},   # 45/50 = 90%
        {"assignment_id": 302, "score": 40.0},   # 40/50 = 80%
        # 201 (Final) intentionally absent
    ]


@pytest.fixture
def sample_weights():
    """Syllabus weights: Midterm 40%, Final 40%, Assignments 20%."""
    return {
        "Midterm": 40.0,
        "Final": 40.0,
        "Assignments": 20.0,
    }


@pytest.fixture
def drop_rule_groups():
    """Assignment group with drop_lowest=1 rule and three graded submissions."""
    return [
        {
            "id": 50,
            "name": "Quizzes",
            "group_weight": 30.0,
            "rules": {"drop_lowest": 1},
            "assignments": [
                {"id": 501, "name": "Quiz 1", "points_possible": 10},
                {"id": 502, "name": "Quiz 2", "points_possible": 10},
                {"id": 503, "name": "Quiz 3", "points_possible": 10},
            ],
        }
    ]


@pytest.fixture
def drop_rule_submissions():
    """Quiz scores: 40%, 70%, 100% — drop_lowest should remove Quiz 1."""
    return [
        {"assignment_id": 501, "score": 4.0},   # 40% — lowest, will be dropped
        {"assignment_id": 502, "score": 7.0},   # 70%
        {"assignment_id": 503, "score": 10.0},  # 100%
    ]


@pytest.fixture
def sample_acorn_data():
    """Two-term ACORN payload: Fall 2023 (completed) + Winter 2024 (one IPR)."""
    return {
        "terms": [
            {
                "term": "Fall 2023",
                "sessionalGpa": 3.5,
                "cumulativeGpa": 3.5,
                "courses": [
                    {
                        "courseCode": "CSCA08H3",
                        "code": "CSCA08H3",
                        "title": "Intro to Computer Programming",
                        "credits": 0.5,
                        "grade": "A",
                        "mark": 85,
                    },
                    {
                        "courseCode": "MATA30H3",
                        "code": "MATA30H3",
                        "title": "Calculus I",
                        "credits": 0.5,
                        "grade": "B+",
                        "mark": 78,
                    },
                ],
            },
            {
                "term": "Winter 2024",
                "sessionalGpa": 3.8,
                "cumulativeGpa": 3.65,
                "courses": [
                    {
                        "courseCode": "CSCA48H3",
                        "code": "CSCA48H3",
                        "title": "Intro to Computer Programming II",
                        "credits": 0.5,
                        "grade": "A+",
                        "mark": 92,
                    },
                    {
                        "courseCode": "STAC32H3",
                        "code": "STAC32H3",
                        "title": "Applications of Statistical Methods",
                        "credits": 0.5,
                        "grade": "IPR",
                        "mark": None,
                    },
                ],
            },
        ]
    }


@pytest.fixture
def sample_requirements():
    """Program requirements dict with required, n_credits_from_list, and open_pool items."""
    return {
        "program_name": "Computer Science Specialist",
        "academic_year": "2024-2025",
        "campus": "UTSC",
        "is_coop": False,
        "program_credits_required": 2.5,
        "degree_credits_required": 20.0,
        "groups": [
            {
                "id": "core",
                "label": "Core Requirements",
                "section": "core",
                "credits_required": 2.5,
                "items": [
                    {
                        "id": "csca08",
                        "type": "required",
                        "courses": ["CSCA08H3"],
                        "credits": 0.5,
                        "label": "Intro to CS I",
                    },
                    {
                        "id": "csca48",
                        "type": "required",
                        "courses": ["CSCA48H3"],
                        "credits": 0.5,
                        "label": "Intro to CS II",
                    },
                    {
                        "id": "intro_calc",
                        "type": "required",
                        "courses": ["MATA30H3", "MATA31H3"],
                        "credits": 0.5,
                        "label": "Calculus I (either section)",
                    },
                    {
                        "id": "stats_list",
                        "type": "n_credits_from_list",
                        "credits_needed": 0.5,
                        "courses": ["STAC32H3", "STAC33H3"],
                        "label": "0.5 cr from STA list",
                    },
                    {
                        "id": "csc_upper",
                        "type": "open_pool",
                        "credits_needed": 0.5,
                        "label": "0.5 cr C-level CSC",
                        "filters": {
                            "departments": ["CSC"],
                            "levels": ["C"],
                        },
                        "exclusions": [],
                    },
                ],
            },
        ],
    }


# ── JWT / auth fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def test_user():
    return {
        "id": "user-abc-123",
        "email": "test@mail.utoronto.ca",
        "name": "Test Student",
        "google_id": "google-sub-999",
    }


@pytest.fixture
def valid_token(test_user):
    """A freshly minted JWT for test_user."""
    from api.services.auth_service import create_access_token
    return create_access_token(test_user)


@pytest.fixture
def auth_headers(valid_token):  # pragma: no cover
    return {"Authorization": f"Bearer {valid_token}"}  # pragma: no cover


# ── FastAPI TestClient ─────────────────────────────────────────────────────────

@pytest.fixture
def test_client():  # pragma: no cover
    """TestClient backed by the real FastAPI app with Supabase mocked."""
    from unittest.mock import patch, MagicMock

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

    with patch("auth.user_store.get_supabase_client", return_value=mock_sb), \
         patch("api.services.acorn_service._get_supabase", return_value=mock_sb), \
         patch("api.services.grades_snapshot_service._get_supabase", return_value=mock_sb):
        from fastapi.testclient import TestClient
        from api.main import app
        yield TestClient(app)
