"""
tests/test_chat_router.py — tests for api/routers/chat.py

Handlers are called directly as Python functions/coroutines with mocked
dependencies (starlette 1.0.0 + fastapi 0.103.2 TestClient transport is broken).
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException


def _user(user_id="u-test"):
    return {
        "user_id": user_id,
        "email": "test@example.com",
        "name": "Test User",
        "google_id": "g-test",
    }


@pytest.fixture(autouse=True)
def _reset_chat_limiter():
    """Reset the in-memory rate limiter between tests."""
    from api.routers.chat import _chat_limiter
    _chat_limiter.storage.reset()
    yield
    _chat_limiter.storage.reset()


# ── _resolve_token ─────────────────────────────────────────────────────────────

class TestResolveToken:
    def test_returns_provided_token(self):
        from api.routers.chat import _resolve_token
        result = _resolve_token("my-token", _user())
        assert result == "my-token"

    def test_returns_saved_token_when_none_provided(self):
        from api.routers.chat import _resolve_token
        with patch("api.routers.chat.get_quercus_token", return_value="saved-tok"):
            result = _resolve_token(None, _user())
        assert result == "saved-tok"

    def test_raises_400_when_no_token_at_all(self):
        from api.routers.chat import _resolve_token
        with patch("api.routers.chat.get_quercus_token", return_value=None):
            with pytest.raises(HTTPException) as exc:
                _resolve_token(None, _user())
        assert exc.value.status_code == 400

    def test_raises_400_on_user_store_error(self):
        from api.routers.chat import _resolve_token
        from api.auth.user_store import UserStoreError
        with patch("api.routers.chat.get_quercus_token", side_effect=UserStoreError("db error")):
            with pytest.raises(HTTPException) as exc:
                _resolve_token(None, _user())
        assert exc.value.status_code == 400


# ── chat (async POST handler) ──────────────────────────────────────────────────

class TestChatHandler:
    async def test_chat_success_no_conversation(self):
        from api.routers.chat import chat, ChatRequest
        payload = ChatRequest(message="hello", quercus_token="tok")
        with patch("api.routers.chat.run_agent", return_value=("agent answer", [])):
            result = await chat(payload, _user())
        assert result["answer"] == "agent answer"
        assert result["conversation_id"] is None

    async def test_chat_with_conversation_id_loads_history(self):
        from api.routers.chat import chat, ChatRequest
        payload = ChatRequest(message="hello", quercus_token="tok", conversation_id="conv-1")
        with patch("api.routers.chat.get_conversation_messages", return_value=[{"role": "user", "text": "hi"}]), \
             patch("api.routers.chat.run_agent", return_value=("answer", [])), \
             patch("api.routers.chat.save_exchange"):
            result = await chat(payload, _user())
        assert result["conversation_id"] == "conv-1"

    async def test_chat_history_load_error_still_proceeds(self):
        from api.routers.chat import chat, ChatRequest
        from api.services.chat_history_service import ChatHistoryServiceError
        payload = ChatRequest(message="hello", quercus_token="tok", conversation_id="conv-1")
        with patch("api.routers.chat.get_conversation_messages", side_effect=ChatHistoryServiceError("err")), \
             patch("api.routers.chat.run_agent", return_value=("answer", [])), \
             patch("api.routers.chat.save_exchange"):
            result = await chat(payload, _user())
        assert "answer" in result

    async def test_chat_agent_exception_raises_500(self):
        from api.routers.chat import chat, ChatRequest
        payload = ChatRequest(message="hello", quercus_token="tok")
        with patch("api.routers.chat.run_agent", side_effect=Exception("agent down")):
            with pytest.raises(HTTPException) as exc:
                await chat(payload, _user())
        assert exc.value.status_code == 500

    async def test_chat_save_exchange_failure_is_swallowed(self):
        from api.routers.chat import chat, ChatRequest
        from api.services.chat_history_service import ChatHistoryServiceError
        payload = ChatRequest(message="hello", quercus_token="tok", conversation_id="conv-1")
        with patch("api.routers.chat.get_conversation_messages", return_value=[]), \
             patch("api.routers.chat.run_agent", return_value=("answer", [])), \
             patch("api.routers.chat.save_exchange", side_effect=ChatHistoryServiceError("save fail")):
            result = await chat(payload, _user())
        assert result["answer"] == "answer"

    async def test_chat_no_conversation_id_skips_save(self):
        from api.routers.chat import chat, ChatRequest
        payload = ChatRequest(message="hello", quercus_token="tok")
        with patch("api.routers.chat.run_agent", return_value=("answer", [])) as mock_agent, \
             patch("api.routers.chat.save_exchange") as mock_save, \
             patch("api.routers.chat.get_conversation_messages") as mock_history:
            result = await chat(payload, _user())
        mock_history.assert_not_called()
        mock_save.assert_not_called()
        assert result["tool_calls"] == []

    async def test_chat_empty_conversation_id_treated_as_none(self):
        from api.routers.chat import chat, ChatRequest
        payload = ChatRequest(message="hello", quercus_token="tok", conversation_id="   ")
        with patch("api.routers.chat.run_agent", return_value=("answer", [])), \
             patch("api.routers.chat.save_exchange") as mock_save:
            result = await chat(payload, _user())
        mock_save.assert_not_called()
        assert result["conversation_id"] is None

    async def test_chat_rate_limit_returns_429(self):
        from api.routers.chat import chat, ChatRequest
        payload = ChatRequest(message="hello", quercus_token="tok")
        with patch("api.routers.chat.run_agent", return_value=("answer", [])):
            for _ in range(10):
                await chat(payload, _user())
            with pytest.raises(HTTPException) as exc:
                await chat(payload, _user())
        assert exc.value.status_code == 429

    async def test_chat_rate_limit_keyed_by_quercus_token(self):
        from api.routers.chat import chat, ChatRequest
        payload_a = ChatRequest(message="hello", quercus_token="token-a")
        payload_b = ChatRequest(message="hello", quercus_token="token-b")
        with patch("api.routers.chat.run_agent", return_value=("answer", [])):
            for _ in range(10):
                await chat(payload_a, _user("user-1"))
            result = await chat(payload_b, _user("user-2"))
        assert result["answer"] == "answer"

    async def test_chat_rate_limit_shared_token_across_users(self):
        from api.routers.chat import chat, ChatRequest
        payload = ChatRequest(message="hello", quercus_token="shared-tok")
        with patch("api.routers.chat.run_agent", return_value=("answer", [])):
            for _ in range(10):
                await chat(payload, _user("user-1"))
            with pytest.raises(HTTPException) as exc:
                await chat(payload, _user("user-2"))
        assert exc.value.status_code == 429


# ── history (GET /api/chat/history) ───────────────────────────────────────────

class TestHistoryHandler:
    def test_returns_conversations_list(self):
        from api.routers.chat import history
        fake_convs = [{"id": "c1", "title": "Chat 1"}, {"id": "c2", "title": "Chat 2"}]
        with patch("api.routers.chat.list_conversations", return_value=fake_convs):
            result = history(current_user=_user())
        assert result == {"conversations": fake_convs}

    def test_raises_400_on_service_error(self):
        from api.routers.chat import history
        from api.services.chat_history_service import ChatHistoryServiceError
        with patch("api.routers.chat.list_conversations", side_effect=ChatHistoryServiceError("fail")):
            with pytest.raises(HTTPException) as exc:
                history(current_user=_user())
        assert exc.value.status_code == 400


# ── history_detail (GET /api/chat/history/{id}) ────────────────────────────────

class TestHistoryDetailHandler:
    def test_returns_conversation_with_messages(self):
        from api.routers.chat import history_detail
        fake = {"id": "c1", "title": "Old chat", "messages": []}
        with patch("api.routers.chat.get_conversation", return_value=fake):
            result = history_detail("c1", current_user=_user())
        assert result == fake

    def test_raises_404_when_not_found(self):
        from api.routers.chat import history_detail
        from api.services.chat_history_service import ChatHistoryServiceError
        with patch("api.routers.chat.get_conversation",
                   side_effect=ChatHistoryServiceError("Chat conversation not found")):
            with pytest.raises(HTTPException) as exc:
                history_detail("c1", current_user=_user())
        assert exc.value.status_code == 404

    def test_raises_400_on_other_service_error(self):
        from api.routers.chat import history_detail
        from api.services.chat_history_service import ChatHistoryServiceError
        with patch("api.routers.chat.get_conversation",
                   side_effect=ChatHistoryServiceError("DB error")):
            with pytest.raises(HTTPException) as exc:
                history_detail("c1", current_user=_user())
        assert exc.value.status_code == 400


# ── history_delete (DELETE /api/chat/history/{id}) ────────────────────────────

class TestHistoryDeleteHandler:
    def test_deletes_and_returns_status(self):
        from api.routers.chat import history_delete
        with patch("api.routers.chat.delete_conversation"):
            result = history_delete("c1", current_user=_user())
        assert result == {"status": "deleted"}

    def test_raises_404_when_not_found(self):
        from api.routers.chat import history_delete
        from api.services.chat_history_service import ChatHistoryServiceError
        with patch("api.routers.chat.delete_conversation",
                   side_effect=ChatHistoryServiceError("Chat conversation not found")):
            with pytest.raises(HTTPException) as exc:
                history_delete("c1", current_user=_user())
        assert exc.value.status_code == 404

    def test_raises_400_on_other_service_error(self):
        from api.routers.chat import history_delete
        from api.services.chat_history_service import ChatHistoryServiceError
        with patch("api.routers.chat.delete_conversation",
                   side_effect=ChatHistoryServiceError("DB connection failed")):
            with pytest.raises(HTTPException) as exc:
                history_delete("c1", current_user=_user())
        assert exc.value.status_code == 400
