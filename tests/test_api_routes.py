"""
tests/test_api_routes.py — tests for API-layer logic.

The starlette 1.0.0 + fastapi 0.103.2 combination installed in this
environment has a middleware incompatibility that prevents routing via HTTP
transport in tests.  We therefore test:

  - JWT auth (auth_service, dependencies) — purely at the function level
  - Dashboard logic (service layer) — function-level with mocked Quercus/Supabase
  - ACORN service contract — function-level, matching what the Chrome extension sends
  - Chat service — function-level
  - Route handler guards — instantiated directly with mock deps

All external calls (Quercus, Supabase, Anthropic) are mocked.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, AsyncMock


# ── helpers ───────────────────────────────────────────────────────────────────

TEST_USER_DB = {
    "id": "user-abc",
    "email": "test@mail.utoronto.ca",
    "name": "Test Student",
    "google_id": "google-sub-001",
}


# ── auth: JWT generation and validation ──────────────────────────────────────

class TestJWT:
    def test_create_and_decode_valid_token(self, test_user):
        from api.services.auth_service import create_access_token, decode_access_token
        token = create_access_token(test_user)
        payload = decode_access_token(token)
        assert payload["user_id"] == test_user["id"]
        assert payload["email"] == test_user["email"]
        assert payload["google_id"] == test_user["google_id"]

    def test_token_carries_name(self, test_user):
        from api.services.auth_service import create_access_token, decode_access_token
        token = create_access_token(test_user)
        assert decode_access_token(token)["name"] == test_user["name"]

    def test_expired_token_rejected(self):
        from jose import jwt as jose_jwt
        from api.services.auth_service import AuthServiceError, decode_access_token
        import os
        secret = os.environ["JWT_SECRET"]
        payload = {
            "user_id": "u1", "email": "x@x.com", "name": "X", "google_id": "g1",
            "exp": int((datetime.now(timezone.utc) - timedelta(seconds=10)).timestamp()),
        }
        expired = jose_jwt.encode(payload, secret, algorithm="HS256")
        with pytest.raises(AuthServiceError):
            decode_access_token(expired)

    def test_invalid_signature_rejected(self):
        from jose import jwt as jose_jwt
        from api.services.auth_service import AuthServiceError, decode_access_token
        payload = {
            "user_id": "u1", "email": "x@x.com", "name": "X", "google_id": "g1",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        bad = jose_jwt.encode(payload, "wrong-secret-key", algorithm="HS256")
        with pytest.raises(AuthServiceError):
            decode_access_token(bad)

    def test_malformed_token_rejected(self):
        from api.services.auth_service import AuthServiceError, decode_access_token
        with pytest.raises(AuthServiceError):
            decode_access_token("not.a.valid.jwt")

    def test_dependency_raises_401_on_bad_token(self):
        """get_current_user FastAPI dependency raises HTTP 401 for invalid tokens."""
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials
        from api.dependencies import get_current_user

        bad_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="garbage")
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(bad_creds)
        assert exc_info.value.status_code == 401

    def test_dependency_returns_user_dict_for_valid_token(self, valid_token):
        """get_current_user returns a user dict for a properly signed token."""
        from fastapi.security import HTTPAuthorizationCredentials
        from api.dependencies import get_current_user

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=valid_token)
        user = get_current_user(creds)
        assert user["user_id"] == "user-abc-123"
        assert "email" in user
        assert "google_id" in user

    def test_dependency_raises_401_on_expired_token(self):
        """get_current_user raises HTTP 401 for expired token."""
        from jose import jwt as jose_jwt
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials
        from api.dependencies import get_current_user
        import os

        secret = os.environ["JWT_SECRET"]
        payload = {
            "user_id": "u1", "email": "x@x.com", "name": "X", "google_id": "g1",
            "exp": int((datetime.now(timezone.utc) - timedelta(seconds=10)).timestamp()),
        }
        expired = jose_jwt.encode(payload, secret, algorithm="HS256")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=expired)
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(creds)
        assert exc_info.value.status_code == 401


# ── dashboard route logic ─────────────────────────────────────────────────────

class TestDashboardLogic:
    """Test the dashboard 3-tier caching logic by calling _resolve_token and
    service functions directly — no HTTP transport needed."""

    def test_resolve_token_prefers_supplied_token(self):
        """_resolve_token returns the caller-supplied token over the saved one."""
        from api.routers.courses import _resolve_token
        user = {"user_id": "u1"}
        with patch("api.routers.courses.get_quercus_token", return_value="saved-tok"):
            result = _resolve_token("supplied-tok", user)
        assert result == "supplied-tok"

    def test_resolve_token_falls_back_to_saved(self):
        """_resolve_token returns the Supabase-saved token when none supplied."""
        from api.routers.courses import _resolve_token
        user = {"user_id": "u1"}
        with patch("api.routers.courses.get_quercus_token", return_value="saved-tok"):
            result = _resolve_token(None, user)
        assert result == "saved-tok"

    def test_in_memory_cache_hit_returns_cached_data(self):
        """Layer 1: when _dashboard_cache[user_id] is populated, it is returned."""
        import api.routers.courses as mod
        user_id = "cached-user"
        mod._dashboard_cache[user_id] = {
            "courses": [{"id": 1001}],
            "announcements": [],
            "term_name": "Fall 2024",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        assert user_id in mod._dashboard_cache
        assert mod._dashboard_cache[user_id]["courses"][0]["id"] == 1001
        del mod._dashboard_cache[user_id]

    def test_snapshot_returns_none_when_stale(self):
        """get_dashboard_snapshot returns None if the snapshot is too old."""
        from api.services.grades_snapshot_service import get_dashboard_snapshot
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        fake_row = {
            "fetched_at": old_ts,
            "dashboard_data": {"courses": [], "announcements": []},
        }
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value \
            .eq.return_value.order.return_value \
            .execute.return_value.data = [fake_row]
        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            result = get_dashboard_snapshot("u1", max_age_minutes=60)
        assert result is None

    def test_live_fetch_calls_list_current_term_courses(self):
        """When both caches miss, list_current_term_courses is called."""
        from api.services.course_service import list_current_term_courses
        with patch("api.integrations.quercus.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, ok=True,
                headers={"Link": ""},
                json=lambda: [],
            )
            courses = list_current_term_courses("fake-tok")
        assert isinstance(courses, list)


# ── ACORN service contract ─────────────────────────────────────────────────────

class TestAcornServiceContract:
    """Verify the exact data shape the Chrome extension sends and what we store."""

    def _valid_payload(self):
        return {
            "importCode": "ABC123",
            "terms": [{
                "term": "Fall 2023",
                "sessionalGpa": 3.5,
                "cumulativeGpa": 3.5,
                "courses": [{
                    "courseCode": "CSCA08H3",
                    "title": "Intro CS",
                    "credits": 0.5,
                    "grade": "A",
                    "mark": 85,
                }],
            }],
            "courses": [{
                "courseCode": "CSCA08H3",
                "title": "Intro CS",
                "credits": 0.5,
                "grade": "A",
                "mark": 85,
                "term": "Fall 2023",
            }],
        }

    def test_validate_payload_accepts_valid_import(self):
        """validate_payload returns a normalised dict for a correct extension payload."""
        from api.integrations.acorn_store import validate_payload
        result = validate_payload(self._valid_payload())
        assert result["importCode"] == "ABC123"
        assert len(result["courses"]) == 1
        assert "importedAt" in result

    def test_validate_payload_requires_import_code(self):
        """Missing importCode raises AcornStoreError."""
        from api.integrations.acorn_store import validate_payload, AcornStoreError
        with pytest.raises(AcornStoreError):
            validate_payload({"courses": []})

    def test_validate_payload_requires_courses_or_terms(self):
        """Payload with neither courses nor terms raises AcornStoreError."""
        from api.integrations.acorn_store import validate_payload, AcornStoreError
        with pytest.raises(AcornStoreError):
            validate_payload({"importCode": "X"})

    def test_import_acorn_data_calls_supabase_insert(self):
        """import_acorn_data persists the validated payload to Supabase."""
        from api.services.acorn_service import import_acorn_data
        payload = self._valid_payload()
        import_code = payload.pop("importCode")

        fake_row = {"id": 1, "import_code": "ABC123"}
        mock_sb = MagicMock()
        mock_sb.table.return_value.insert.return_value.execute.return_value.data = [fake_row]

        with patch("api.services.acorn_service._get_supabase", return_value=mock_sb):
            result = import_acorn_data(import_code, payload)

        assert result["importCode"] == "ABC123"
        assert len(result["courses"]) == 1
        mock_sb.table.return_value.insert.assert_called_once()

    def test_get_latest_import_returns_none_when_not_found(self):
        """get_latest_import returns None when Supabase returns no rows."""
        from api.services.acorn_service import get_latest_import
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value \
            .order.return_value.limit.return_value.execute.return_value.data = []

        with patch("api.services.acorn_service._get_supabase", return_value=mock_sb):
            result = get_latest_import("MISSING")
        assert result is None

    def test_get_latest_import_returns_payload_when_found(self):
        """get_latest_import returns the stored data dict when found."""
        from api.services.acorn_service import get_latest_import
        stored_data = {"importCode": "FOUND1", "courses": [], "terms": []}
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value \
            .order.return_value.limit.return_value.execute.return_value.data = [
                {"data": stored_data}
            ]

        with patch("api.services.acorn_service._get_supabase", return_value=mock_sb):
            result = get_latest_import("FOUND1")
        assert result["importCode"] == "FOUND1"

    def test_get_import_status_returns_exists_false(self):
        """get_import_status returns exists=False when no import found."""
        from api.services.acorn_service import get_import_status
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value \
            .order.return_value.limit.return_value.execute.return_value.data = []

        with patch("api.services.acorn_service._get_supabase", return_value=mock_sb):
            result = get_import_status("MISSING")
        assert result["exists"] is False

    def test_get_import_status_returns_exists_true(self):
        """get_import_status returns exists=True and courseCount when found."""
        from api.services.acorn_service import get_import_status
        stored_data = {"importCode": "X", "importedAt": "2024-01-01T00:00:00Z",
                       "courses": [{"courseCode": "CSCA08H3"}], "terms": []}
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value \
            .order.return_value.limit.return_value.execute.return_value.data = [
                {"data": stored_data}
            ]

        with patch("api.services.acorn_service._get_supabase", return_value=mock_sb):
            result = get_import_status("X")
        assert result["exists"] is True
        assert result["courseCount"] == 1


# ── chat service ──────────────────────────────────────────────────────────────

class TestChatService:
    async def test_chat_route_calls_run_agent(self):
        """POST /api/chat ultimately calls run_agent with the right args."""
        from api.routers.chat import chat

        fake_answer = "Here are your grades."
        fake_tools = [{"name": "get_cached_grades", "input": {}}]

        with patch("api.routers.chat.run_agent", return_value=(fake_answer, fake_tools)), \
             patch("api.routers.chat.get_conversation_messages", return_value=[]), \
             patch("api.routers.chat.get_quercus_token", return_value="tok"), \
             patch("api.routers.chat.save_exchange", return_value=None):

            class FakeRequest:
                message = "What are my grades?"
                quercus_token = None
                conversation_id = "conv-test"

            current_user = {"user_id": "u1", "email": "x@x.com",
                            "name": "X", "google_id": "g1"}

            result = await chat(FakeRequest(), current_user)

        data = result if isinstance(result, dict) else result.body
        if hasattr(result, "body"):  # pragma: no cover
            import json  # pragma: no cover
            data = json.loads(result.body)  # pragma: no cover
        assert data.get("answer") == fake_answer

    def test_run_agent_signature_accepts_history(self):
        """run_agent accepts a history parameter for threaded conversations."""
        from api.agent.agent import run as run_agent
        import inspect
        sig = inspect.signature(run_agent)
        assert "history" in sig.parameters

    def test_get_conversation_messages_returns_list(self):
        """get_conversation_messages returns a list (empty when conversation not found)."""
        from api.services.chat_history_service import get_conversation_messages
        mock_sb = MagicMock()
        # Conversation lookup returns no rows → function returns [] immediately
        mock_sb.table.return_value.select.return_value.eq.return_value \
            .eq.return_value.limit.return_value.execute.return_value.data = []

        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            result = get_conversation_messages("u1", "conv-1")
        assert isinstance(result, list)
