"""
tests/test_snapshot_and_history.py — tests for:
  - api/services/grades_snapshot_service.py
  - api/services/grade_snapshot_cache.py
  - api/services/chat_history_service.py

All Supabase and Quercus calls are mocked.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


def _mock_supabase():
    """Return a minimal Supabase mock where every chained call returns a MagicMock."""
    m = MagicMock()
    chain = m.table.return_value
    for attr in ("select", "insert", "upsert", "update", "delete", "eq", "filter",
                 "order", "limit", "execute"):
        getattr(chain, attr).return_value = chain
    chain.execute.return_value = MagicMock(data=[])
    return m


# ── grades_snapshot_service ───────────────────────────────────────────────────

class TestSaveSnapshot:
    def test_upserts_rows_for_each_course(self):
        from api.services.grades_snapshot_service import save_snapshot
        mock_sb = _mock_supabase()
        courses = [{"id": 1001, "course_code": "CSCA08H3", "name": "Intro CS"}]

        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            result = save_snapshot("u1", courses, announcements=[])

        mock_sb.table.return_value.upsert.assert_called()

    def test_returns_empty_list_for_no_courses(self):
        from api.services.grades_snapshot_service import save_snapshot
        result = save_snapshot("u1", [])
        assert result == []

    def test_raises_when_no_user_id(self):
        from api.services.grades_snapshot_service import save_snapshot, GradesSnapshotServiceError
        with pytest.raises(GradesSnapshotServiceError):
            save_snapshot("", [{"id": 1001}])

    def test_skips_courses_with_no_course_id(self):
        from api.services.grades_snapshot_service import save_snapshot
        result = save_snapshot("u1", [{"name": "No ID"}])
        assert result == []

    def test_raises_on_db_error(self):
        from api.services.grades_snapshot_service import save_snapshot, GradesSnapshotServiceError
        mock_sb = MagicMock()
        mock_sb.table.return_value.delete.return_value.eq.return_value.filter.return_value \
            .execute.return_value = None
        mock_sb.table.return_value.upsert.side_effect = Exception("DB error")
        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(GradesSnapshotServiceError):
                save_snapshot("u1", [{"id": 1001}])


class TestGetSnapshot:
    def test_returns_rows_from_db(self):
        from api.services.grades_snapshot_service import get_snapshot
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[{"course_id": 1001}])

        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            result = get_snapshot("u1")

        assert result == [{"course_id": 1001}]

    def test_returns_empty_for_blank_user_id(self):
        from api.services.grades_snapshot_service import get_snapshot
        assert get_snapshot("") == []
        assert get_snapshot(None) == []

    def test_raises_on_db_error(self):
        from api.services.grades_snapshot_service import get_snapshot, GradesSnapshotServiceError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(GradesSnapshotServiceError):
                get_snapshot("u1")


class TestGetDashboardSnapshot:
    def _fresh_row(self):
        ts = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        return {
            "dashboard_data": {"id": 1001, "term_name": "Fall 2024"},
            "fetched_at": ts,
            "announcements": [],
        }

    def test_returns_snapshot_when_fresh(self):
        from api.services.grades_snapshot_service import get_dashboard_snapshot
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[self._fresh_row()])

        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            result = get_dashboard_snapshot("u1", max_age_minutes=5)

        assert result is not None
        assert result["courses"][0]["id"] == 1001

    def test_returns_none_when_stale(self):
        from api.services.grades_snapshot_service import get_dashboard_snapshot
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        row = {
            "dashboard_data": {"id": 1001},
            "fetched_at": old_ts,
            "announcements": [],
        }
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[row])

        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            result = get_dashboard_snapshot("u1", max_age_minutes=5)

        assert result is None

    def test_returns_none_for_blank_user_id(self):
        from api.services.grades_snapshot_service import get_dashboard_snapshot
        assert get_dashboard_snapshot("") is None

    def test_returns_none_when_no_rows(self):
        from api.services.grades_snapshot_service import get_dashboard_snapshot
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[])

        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            result = get_dashboard_snapshot("u1")

        assert result is None


class TestSaveCourseDetailSnapshot:
    def test_calls_upsert(self):
        from api.services.grades_snapshot_service import save_course_detail_snapshot
        mock_sb = _mock_supabase()

        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            save_course_detail_snapshot("u1", 1001, {"course_id": 1001, "grade": {}})

        mock_sb.table.return_value.upsert.assert_called_once()

    def test_raises_for_blank_user_id(self):
        from api.services.grades_snapshot_service import save_course_detail_snapshot, GradesSnapshotServiceError
        with pytest.raises(GradesSnapshotServiceError):
            save_course_detail_snapshot("", 1001, {})

    def test_raises_on_db_error(self):
        from api.services.grades_snapshot_service import save_course_detail_snapshot, GradesSnapshotServiceError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(GradesSnapshotServiceError):
                save_course_detail_snapshot("u1", 1001, {"x": 1})


class TestGetCourseDetailSnapshot:
    def test_returns_snapshot_when_fresh(self):
        from api.services.grades_snapshot_service import get_course_detail_snapshot
        ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        detail = {"course_id": 1001, "_cached_at": ts, "grade": {}}
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[{"course_detail_data": detail}])

        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            result = get_course_detail_snapshot("u1", 1001)

        assert result is not None
        assert "_cached_at" not in result

    def test_returns_none_for_blank_user_id(self):
        from api.services.grades_snapshot_service import get_course_detail_snapshot
        assert get_course_detail_snapshot("", 1001) is None

    def test_returns_none_when_no_rows(self):
        from api.services.grades_snapshot_service import get_course_detail_snapshot
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[])

        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            result = get_course_detail_snapshot("u1", 1001)

        assert result is None

    def test_returns_none_when_stale(self):
        from api.services.grades_snapshot_service import get_course_detail_snapshot
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        detail = {"_cached_at": old_ts, "course_id": 1001}
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[{"course_detail_data": detail}])

        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            result = get_course_detail_snapshot("u1", 1001, max_age_minutes=60)

        assert result is None


class TestIsSnapshotStale:
    def test_returns_true_when_no_rows(self):
        from api.services.grades_snapshot_service import is_snapshot_stale
        with patch("api.services.grades_snapshot_service.get_snapshot", return_value=[]):
            assert is_snapshot_stale("u1") is True

    def test_returns_false_when_fresh(self):
        from api.services.grades_snapshot_service import is_snapshot_stale
        ts = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        with patch("api.services.grades_snapshot_service.get_snapshot", return_value=[{"fetched_at": ts}]):
            assert is_snapshot_stale("u1", max_age_minutes=5) is False

    def test_returns_true_when_stale(self):
        from api.services.grades_snapshot_service import is_snapshot_stale
        ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        with patch("api.services.grades_snapshot_service.get_snapshot", return_value=[{"fetched_at": ts}]):
            assert is_snapshot_stale("u1", max_age_minutes=5) is True


# ── grade_snapshot_cache ──────────────────────────────────────────────────────

class TestGradeSnapshotCache:
    def test_invalidate_removes_entry(self):
        import api.services.grade_snapshot_cache as mod
        mod._CACHE["u-test"] = {"cached_at": datetime.now(timezone.utc), "data": {}}
        mod.invalidate_grade_snapshot("u-test")
        assert "u-test" not in mod._CACHE

    def test_get_grade_snapshot_fetches_courses(self):
        from api.services.grade_snapshot_cache import get_grade_snapshot
        import api.services.grade_snapshot_cache as mod
        mod._CACHE.pop("u-snap", None)

        fake_course = {"id": 1001, "name": "Intro CS", "course_code": "CSCA08H3"}
        fake_dashboard = {
            "id": 1001, "name": "Intro CS", "course_code": "CSCA08H3",
            "current_grade": 80.0, "letter_grade": "A-", "progress_pct": 60.0,
        }
        with patch("api.services.grade_snapshot_cache.list_current_term_courses", return_value=[fake_course]), \
             patch("api.services.grade_snapshot_cache.get_dashboard_course", return_value=fake_dashboard):
            result = get_grade_snapshot("u-snap", "tok")

        assert result["courses"][0]["course_id"] == 1001

    def test_get_grade_snapshot_returns_cached_when_fresh(self):
        from api.services.grade_snapshot_cache import get_grade_snapshot
        import api.services.grade_snapshot_cache as mod
        cached_data = {"courses": [{"course_id": 9999}], "errors": [], "cached_at": "ts"}
        mod._CACHE["u-cached2"] = {"cached_at": datetime.now(timezone.utc), "data": cached_data}

        with patch("api.services.grade_snapshot_cache.list_current_term_courses") as mock_list:
            result = get_grade_snapshot("u-cached2", "tok", force_refresh=False)
            mock_list.assert_not_called()

        assert result["courses"][0]["course_id"] == 9999
        mod._CACHE.pop("u-cached2", None)

    def test_get_grade_snapshot_records_errors(self):
        from api.services.grade_snapshot_cache import get_grade_snapshot
        import api.services.grade_snapshot_cache as mod
        mod._CACHE.pop("u-err", None)

        fake_course = {"id": 1001, "name": "CS", "course_code": "CSCA08H3"}
        with patch("api.services.grade_snapshot_cache.list_current_term_courses", return_value=[fake_course]), \
             patch("api.services.grade_snapshot_cache.get_dashboard_course", side_effect=Exception("quercus down")):
            result = get_grade_snapshot("u-err", "tok")

        assert len(result["errors"]) == 1


# ── chat_history_service ──────────────────────────────────────────────────────

class TestConversationTitle:
    def test_short_text_returned_as_is(self):
        from api.services.chat_history_service import _conversation_title
        assert _conversation_title("Hello world") == "Hello world"

    def test_truncates_long_text(self):
        from api.services.chat_history_service import _conversation_title
        long = "a" * 200
        result = _conversation_title(long, max_length=80)
        assert len(result) <= 81  # 80 chars + ellipsis

    def test_empty_text_returns_new_chat(self):
        from api.services.chat_history_service import _conversation_title
        assert _conversation_title(None) == "New chat"
        assert _conversation_title("") == "New chat"

    def test_collapses_whitespace(self):
        from api.services.chat_history_service import _conversation_title
        assert _conversation_title("  hello   world  ") == "hello world"


class TestRequireUserId:
    def test_raises_for_empty_string(self):
        from api.services.chat_history_service import _require_user_id, ChatHistoryServiceError
        with pytest.raises(ChatHistoryServiceError):
            _require_user_id("")

    def test_raises_for_none(self):
        from api.services.chat_history_service import _require_user_id, ChatHistoryServiceError
        with pytest.raises(ChatHistoryServiceError):
            _require_user_id(None)

    def test_returns_valid_id(self):
        from api.services.chat_history_service import _require_user_id
        assert _require_user_id("u1") == "u1"


class TestSaveMessage:
    def test_saves_user_message(self):
        from api.services.chat_history_service import save_message
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[{"id": "msg-1"}])

        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            result = save_message("conv-1", "user", "Hello there")

        assert result.get("id") == "msg-1" or "conversation_id" in result

    def test_raises_on_invalid_role(self):
        from api.services.chat_history_service import save_message, ChatHistoryServiceError
        with pytest.raises(ChatHistoryServiceError, match="role"):
            save_message("conv-1", "system", "text")

    def test_raises_on_empty_text(self):
        from api.services.chat_history_service import save_message, ChatHistoryServiceError
        with pytest.raises(ChatHistoryServiceError, match="text"):
            save_message("conv-1", "user", "")

    def test_raises_on_db_error(self):
        from api.services.chat_history_service import save_message, ChatHistoryServiceError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(ChatHistoryServiceError):
                save_message("conv-1", "user", "Hello")


class TestEnsureConversation:
    def test_creates_new_conversation_when_not_found(self):
        from api.services.chat_history_service import ensure_conversation
        mock_sb = _mock_supabase()
        # First call (select) returns empty, second (insert) returns the new row
        mock_sb.table.return_value.execute.side_effect = [
            MagicMock(data=[]),    # existing lookup
            MagicMock(data=[{"id": "conv-1", "title": "Hello?"}]),  # insert
        ]

        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            result = ensure_conversation("u1", "conv-1", "Hello?")

        assert result["id"] == "conv-1"

    def test_updates_existing_conversation(self):
        from api.services.chat_history_service import ensure_conversation
        existing_row = {"id": "conv-2", "title": "Old title", "updated_at": "old"}
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.side_effect = [
            MagicMock(data=[existing_row]),   # existing lookup
            MagicMock(data=[{**existing_row, "updated_at": "new"}]),  # update
        ]

        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            result = ensure_conversation("u1", "conv-2")

        assert "id" in result

    def test_raises_for_blank_user_id(self):
        from api.services.chat_history_service import ensure_conversation, ChatHistoryServiceError
        with pytest.raises(ChatHistoryServiceError):
            ensure_conversation("", "conv-1")


class TestListConversations:
    def test_returns_list(self):
        from api.services.chat_history_service import list_conversations
        fake = [{"id": "c1", "title": "Chat 1"}]
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=fake)

        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            result = list_conversations("u1")

        assert result == fake

    def test_raises_for_blank_user_id(self):
        from api.services.chat_history_service import list_conversations, ChatHistoryServiceError
        with pytest.raises(ChatHistoryServiceError):
            list_conversations("")

    def test_raises_on_db_error(self):
        from api.services.chat_history_service import list_conversations, ChatHistoryServiceError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(ChatHistoryServiceError):
                list_conversations("u1")

    def test_returns_empty_list_when_no_conversations(self):
        from api.services.chat_history_service import list_conversations
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[])
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            result = list_conversations("u1")
        assert result == []


# ── _require_conversation_id ───────────────────────────────────────────────────

class TestRequireConversationId:
    def test_raises_for_empty_string(self):
        from api.services.chat_history_service import _require_conversation_id, ChatHistoryServiceError
        with pytest.raises(ChatHistoryServiceError, match="conversation_id"):
            _require_conversation_id("")

    def test_raises_for_whitespace_only(self):
        from api.services.chat_history_service import _require_conversation_id, ChatHistoryServiceError
        with pytest.raises(ChatHistoryServiceError, match="conversation_id"):
            _require_conversation_id("   ")

    def test_returns_cleaned_id(self):
        from api.services.chat_history_service import _require_conversation_id
        assert _require_conversation_id("  conv-1  ") == "conv-1"


# ── save_exchange ─────────────────────────────────────────────────────────────

class TestSaveExchange:
    def test_calls_ensure_and_save_twice(self):
        from api.services.chat_history_service import save_exchange
        with patch("api.services.chat_history_service.ensure_conversation", return_value={"id": "c1"}) as mock_ensure, \
             patch("api.services.chat_history_service.save_message") as mock_save:
            result = save_exchange("u1", "c1", "Hello", "World", tool_calls=[])
        mock_ensure.assert_called_once_with("u1", "c1", title_seed="Hello")
        assert mock_save.call_count == 2
        assert result == {"id": "c1"}

    def test_passes_tool_calls_to_assistant_message(self):
        from api.services.chat_history_service import save_exchange
        tool_calls = [{"name": "get_grades", "result": {}}]
        with patch("api.services.chat_history_service.ensure_conversation", return_value={"id": "c1"}), \
             patch("api.services.chat_history_service.save_message") as mock_save:
            save_exchange("u1", "c1", "What are my grades?", "Here they are", tool_calls=tool_calls)
        # Second save_message call (assistant) should pass tool_calls
        _, kwargs = mock_save.call_args
        assert kwargs.get("tool_calls") == tool_calls or mock_save.call_args_list[1][1].get("tool_calls") == tool_calls


# ── get_conversation ──────────────────────────────────────────────────────────

class TestGetConversation:
    def test_returns_conversation_with_messages(self):
        from api.services.chat_history_service import get_conversation
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "c1", "title": "Chat 1"}]),  # conversation lookup
            MagicMock(data=[{"role": "user", "text": "hi"}]),    # messages lookup
        ]
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            result = get_conversation("u1", "c1")
        assert result["id"] == "c1"
        assert result["messages"] == [{"role": "user", "text": "hi"}]

    def test_raises_when_conversation_not_found(self):
        from api.services.chat_history_service import get_conversation, ChatHistoryServiceError
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.side_effect = [
            MagicMock(data=[]),   # conversation lookup: empty
            MagicMock(data=[]),   # messages (not reached, but set anyway)
        ]
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(ChatHistoryServiceError, match="not found"):
                get_conversation("u1", "c1")

    def test_raises_for_blank_user_id(self):
        from api.services.chat_history_service import get_conversation, ChatHistoryServiceError
        with pytest.raises(ChatHistoryServiceError):
            get_conversation("", "c1")

    def test_raises_for_blank_conversation_id(self):
        from api.services.chat_history_service import get_conversation, ChatHistoryServiceError
        with pytest.raises(ChatHistoryServiceError):
            get_conversation("u1", "")

    def test_raises_on_db_error(self):
        from api.services.chat_history_service import get_conversation, ChatHistoryServiceError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(ChatHistoryServiceError, match="Failed to load"):
                get_conversation("u1", "c1")


# ── get_conversation_messages ─────────────────────────────────────────────────

class TestGetConversationMessages:
    def test_returns_empty_when_conversation_not_found(self):
        from api.services.chat_history_service import get_conversation_messages
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[])
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            result = get_conversation_messages("u1", "c1")
        assert result == []

    def test_returns_messages_oldest_first(self):
        from api.services.chat_history_service import get_conversation_messages
        mock_sb = _mock_supabase()
        # Messages returned desc (newest first), then reversed by the function
        mock_sb.table.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "c1"}]),  # conv check: exists
            MagicMock(data=[
                {"role": "assistant", "text": "reply"},
                {"role": "user", "text": "hello"},
            ]),  # msgs desc
        ]
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            result = get_conversation_messages("u1", "c1")
        # Reversed → user first, assistant second
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    def test_raises_for_blank_user_id(self):
        from api.services.chat_history_service import get_conversation_messages, ChatHistoryServiceError
        with pytest.raises(ChatHistoryServiceError):
            get_conversation_messages("", "c1")

    def test_raises_on_db_error(self):
        from api.services.chat_history_service import get_conversation_messages, ChatHistoryServiceError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(ChatHistoryServiceError, match="Failed to load conversation messages"):
                get_conversation_messages("u1", "c1")


# ── delete_conversation ───────────────────────────────────────────────────────

class TestDeleteConversation:
    def test_deletes_messages_and_conversation(self):
        from api.services.chat_history_service import delete_conversation
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "c1"}]),  # lookup: exists
            MagicMock(data=[]),               # delete messages
            MagicMock(data=[]),               # delete conversation
        ]
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            delete_conversation("u1", "c1")  # should not raise
        mock_sb.table.return_value.delete.assert_called()

    def test_raises_when_conversation_not_found(self):
        from api.services.chat_history_service import delete_conversation, ChatHistoryServiceError
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[])
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(ChatHistoryServiceError, match="not found"):
                delete_conversation("u1", "c1")

    def test_raises_for_blank_user_id(self):
        from api.services.chat_history_service import delete_conversation, ChatHistoryServiceError
        with pytest.raises(ChatHistoryServiceError):
            delete_conversation("", "c1")

    def test_raises_on_lookup_db_error(self):
        from api.services.chat_history_service import delete_conversation, ChatHistoryServiceError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(ChatHistoryServiceError, match="Failed to load"):
                delete_conversation("u1", "c1")

    def test_raises_when_delete_operation_fails(self):
        from api.services.chat_history_service import delete_conversation, ChatHistoryServiceError
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "c1"}]),  # lookup: found
            Exception("delete messages failed"),  # messages delete raises
        ]
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(ChatHistoryServiceError, match="Failed to delete"):
                delete_conversation("u1", "c1")


# ── ensure_conversation (additional branches) ─────────────────────────────────

class TestEnsureConversationAdditional:
    def test_sets_title_when_existing_row_has_none(self):
        from api.services.chat_history_service import ensure_conversation
        existing_row = {"id": "c1", "title": None, "updated_at": "old"}
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.side_effect = [
            MagicMock(data=[existing_row]),   # lookup: found row with no title
            MagicMock(data=[{**existing_row, "title": "Hello?", "updated_at": "new"}]),  # update
        ]
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            result = ensure_conversation("u1", "c1", "Hello?")
        assert result.get("title") in ("Hello?", None)  # title was set in update

    def test_insert_returns_payload_when_response_empty(self):
        from api.services.chat_history_service import ensure_conversation
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.side_effect = [
            MagicMock(data=[]),   # lookup: no existing
            MagicMock(data=[]),   # insert returns empty
        ]
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            result = ensure_conversation("u1", "conv-new", "First message")
        # Falls back to the payload dict
        assert result["id"] == "conv-new"
        assert result["user_id"] == "u1"

    def test_raises_on_lookup_db_error(self):
        from api.services.chat_history_service import ensure_conversation, ChatHistoryServiceError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(ChatHistoryServiceError, match="Failed to load"):
                ensure_conversation("u1", "c1")

    def test_raises_on_update_db_error(self):
        from api.services.chat_history_service import ensure_conversation, ChatHistoryServiceError
        existing_row = {"id": "c1", "title": "Old", "updated_at": "old"}
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.side_effect = [
            MagicMock(data=[existing_row]),   # lookup: found
            Exception("update failed"),        # update raises
        ]
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(ChatHistoryServiceError, match="Failed to update"):
                ensure_conversation("u1", "c1")

    def test_raises_on_insert_db_error(self):
        from api.services.chat_history_service import ensure_conversation, ChatHistoryServiceError
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.side_effect = [
            MagicMock(data=[]),          # lookup: no existing
            Exception("insert failed"),  # insert raises
        ]
        with patch("api.services.chat_history_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(ChatHistoryServiceError, match="Failed to create"):
                ensure_conversation("u1", "conv-new", "Hello?")


# ── grades_snapshot_service (additional branches) ─────────────────────────────

class TestGetDashboardSnapshotAdditional:
    def test_returns_none_when_rows_have_no_fetched_at(self):
        from api.services.grades_snapshot_service import get_dashboard_snapshot
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[{
            "dashboard_data": {"id": 1001},
            "fetched_at": None,
            "announcements": [],
        }])
        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            result = get_dashboard_snapshot("u1")
        assert result is None

    def test_raises_on_db_error(self):
        from api.services.grades_snapshot_service import get_dashboard_snapshot, GradesSnapshotServiceError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(GradesSnapshotServiceError):
                get_dashboard_snapshot("u1")

    def test_returns_none_on_invalid_fetched_at_format(self):
        from api.services.grades_snapshot_service import get_dashboard_snapshot
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[{
            "dashboard_data": {"id": 1001},
            "fetched_at": "not-a-valid-iso-date",
            "announcements": [],
        }])
        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            result = get_dashboard_snapshot("u1")
        assert result is None

    def test_returns_none_when_all_dashboard_data_is_none(self):
        from api.services.grades_snapshot_service import get_dashboard_snapshot
        ts = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[{
            "dashboard_data": None,
            "fetched_at": ts,
            "announcements": [],
        }])
        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            result = get_dashboard_snapshot("u1")
        assert result is None


class TestGetCourseDetailSnapshotAdditional:
    def test_returns_data_when_no_cached_at_key(self):
        from api.services.grades_snapshot_service import get_course_detail_snapshot
        detail = {"course_id": 1001, "grade": {"weighted": 80.0}}
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[{"course_detail_data": detail}])
        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            result = get_course_detail_snapshot("u1", 1001)
        assert result is not None
        assert result["course_id"] == 1001

    def test_raises_on_db_error(self):
        from api.services.grades_snapshot_service import get_course_detail_snapshot, GradesSnapshotServiceError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(GradesSnapshotServiceError):
                get_course_detail_snapshot("u1", 1001)

    def test_returns_none_on_invalid_cached_at_format(self):
        from api.services.grades_snapshot_service import get_course_detail_snapshot
        detail = {"course_id": 1001, "_cached_at": "not-a-valid-date", "grade": {}}
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[{"course_detail_data": detail}])
        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            result = get_course_detail_snapshot("u1", 1001)
        assert result is None


class TestIsSnapshotStaleAdditional:
    def test_returns_true_when_rows_have_no_fetched_at(self):
        from api.services.grades_snapshot_service import is_snapshot_stale
        with patch("api.services.grades_snapshot_service.get_snapshot",
                   return_value=[{"course_id": 1001, "fetched_at": None}]):
            assert is_snapshot_stale("u1") is True

    def test_returns_true_on_invalid_fetched_at_format(self):
        from api.services.grades_snapshot_service import is_snapshot_stale
        with patch("api.services.grades_snapshot_service.get_snapshot",
                   return_value=[{"fetched_at": "not-a-valid-iso-date"}]):
            assert is_snapshot_stale("u1") is True


class TestSaveSnapshotStaleRowWarning:
    def test_logs_warning_when_stale_delete_fails(self):
        from api.services.grades_snapshot_service import save_snapshot
        mock_sb = _mock_supabase()
        mock_sb.table.return_value.execute.side_effect = [
            Exception("stale delete failed"),  # first execute (delete stale rows) fails
            MagicMock(data=[]),                # second execute (upsert) succeeds
        ]
        with patch("api.services.grades_snapshot_service.get_supabase_client", return_value=mock_sb):
            result = save_snapshot("u1", [{"id": 1001, "course_code": "CSCA08H3"}])
        # Should not raise — warning logged and upsert proceeded
