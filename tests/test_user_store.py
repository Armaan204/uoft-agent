"""
tests/test_user_store.py — unit tests for auth/user_store.py.

All Supabase calls are mocked.  Fernet encryption uses a real (test-only) key
so encrypt/decrypt round-trips actually work.
"""

import base64
import os
import pytest
from unittest.mock import MagicMock, patch

# A valid Fernet key (URL-safe base64-encoded 32 zero bytes)
_FERNET_KEY = base64.urlsafe_b64encode(b"\x00" * 32).decode()


@pytest.fixture(autouse=True)
def fernet_env(monkeypatch):
    """Override ENCRYPTION_KEY with a real Fernet key for these tests."""
    monkeypatch.setenv("ENCRYPTION_KEY", _FERNET_KEY)


def _mock_sb():
    return MagicMock()


# ── get_or_create_user ────────────────────────────────────────────────────────

class TestGetOrCreateUser:
    def test_returns_row_when_upsert_succeeds(self):
        from auth.user_store import get_or_create_user
        fake_row = {"id": "u1", "google_id": "g1", "email": "test@example.com"}
        mock_sb = _mock_sb()
        mock_sb.table.return_value.upsert.return_value.execute.return_value.data = [fake_row]

        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            result = get_or_create_user("g1", "test@example.com")

        assert result["id"] == "u1"

    def test_fallback_lookup_when_upsert_returns_no_data(self):
        """When upsert returns empty data, falls back to a SELECT query."""
        from auth.user_store import get_or_create_user
        fake_row = {"id": "u2", "google_id": "g2", "email": "other@example.com"}
        mock_sb = _mock_sb()
        # upsert returns no data
        mock_sb.table.return_value.upsert.return_value.execute.return_value.data = []
        # lookup returns the row
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value \
            .execute.return_value.data = [fake_row]

        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            result = get_or_create_user("g2", "other@example.com")

        assert result["google_id"] == "g2"

    def test_empty_google_id_raises(self):
        from auth.user_store import get_or_create_user, UserStoreError
        with pytest.raises(UserStoreError):
            get_or_create_user("", "test@example.com")

    def test_whitespace_google_id_raises(self):
        from auth.user_store import get_or_create_user, UserStoreError
        with pytest.raises(UserStoreError):
            get_or_create_user("   ", "test@example.com")

    def test_upsert_exception_raises_user_store_error(self):
        from auth.user_store import get_or_create_user, UserStoreError
        mock_sb = _mock_sb()
        mock_sb.table.return_value.upsert.return_value.execute.side_effect = Exception("DB down")

        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            with pytest.raises(UserStoreError, match="Failed to upsert"):
                get_or_create_user("g1", "test@example.com")

    def test_lookup_exception_after_empty_upsert_raises(self):
        from auth.user_store import get_or_create_user, UserStoreError
        mock_sb = _mock_sb()
        mock_sb.table.return_value.upsert.return_value.execute.return_value.data = []
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = Exception("lookup fail")
        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            with pytest.raises(UserStoreError, match="Failed to load user after upsert"):
                get_or_create_user("g2", "test@example.com")


# ── save_quercus_token ────────────────────────────────────────────────────────

class TestSaveQuercusToken:
    def test_inserts_new_token_when_none_exists(self):
        from auth.user_store import save_quercus_token
        mock_sb = _mock_sb()
        # No existing token
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value \
            .execute.return_value.data = []

        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            save_quercus_token("u1", "my-token")

        mock_sb.table.return_value.insert.assert_called_once()

    def test_updates_existing_token(self):
        from auth.user_store import save_quercus_token
        mock_sb = _mock_sb()
        # Existing token row
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value \
            .execute.return_value.data = [{"id": "row-1"}]

        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            save_quercus_token("u1", "my-new-token")

        mock_sb.table.return_value.update.assert_called_once()

    def test_raises_on_empty_user_id(self):
        from auth.user_store import save_quercus_token, UserStoreError
        with pytest.raises(UserStoreError):
            save_quercus_token("", "tok")

    def test_raises_on_none_user_id(self):
        from auth.user_store import save_quercus_token, UserStoreError
        with pytest.raises(UserStoreError):
            save_quercus_token(None, "tok")

    def test_token_is_encrypted_before_storage(self):
        """The raw token string must not appear in the insert payload."""
        from auth.user_store import save_quercus_token
        mock_sb = _mock_sb()
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value \
            .execute.return_value.data = []

        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            save_quercus_token("u1", "plaintext-secret-token")

        insert_call = mock_sb.table.return_value.insert.call_args
        payload = insert_call[0][0]
        assert payload["token"] != "plaintext-secret-token"
        assert "plaintext-secret-token" not in payload["token"]

    def test_update_overwrites_existing_encrypted_token(self):
        from auth.user_store import save_quercus_token
        mock_sb = _mock_sb()
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"id": "row-1"}]
        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            save_quercus_token("u1", "fresh-token")
        payload = mock_sb.table.return_value.update.call_args[0][0]
        assert payload["token"] != "fresh-token"


# ── get_quercus_token ─────────────────────────────────────────────────────────

class TestGetQuercusToken:
    def test_returns_none_for_empty_user_id(self):
        from auth.user_store import get_quercus_token
        assert get_quercus_token("") is None

    def test_returns_none_for_none_user_id(self):
        from auth.user_store import get_quercus_token
        assert get_quercus_token(None) is None

    def test_returns_none_when_no_row(self):
        from auth.user_store import get_quercus_token
        mock_sb = _mock_sb()
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value \
            .execute.return_value.data = []

        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            result = get_quercus_token("u1")
        assert result is None

    def test_decrypts_and_returns_token(self):
        """A token encrypted with the test key can be decrypted back."""
        from auth.user_store import save_quercus_token, get_quercus_token
        plaintext = "my-secret-quercus-token"

        # Save via the real save_quercus_token to get a properly encrypted value
        captured_encrypted = {}
        mock_sb_save = _mock_sb()
        mock_sb_save.table.return_value.select.return_value.eq.return_value.limit.return_value \
            .execute.return_value.data = []

        def capture_insert(payload):
            captured_encrypted["token"] = payload["token"]
            return mock_sb_save.table.return_value.insert.return_value

        mock_sb_save.table.return_value.insert.side_effect = capture_insert

        with patch("auth.user_store.get_supabase_client", return_value=mock_sb_save):
            save_quercus_token("u1", plaintext)

        # Now retrieve it
        mock_sb_get = _mock_sb()
        mock_sb_get.table.return_value.select.return_value.eq.return_value.limit.return_value \
            .execute.return_value.data = [{"token": captured_encrypted["token"]}]

        with patch("auth.user_store.get_supabase_client", return_value=mock_sb_get):
            result = get_quercus_token("u1")

        assert result == plaintext

    def test_raises_on_corrupted_encrypted_token(self):
        from auth.user_store import get_quercus_token, UserStoreError
        mock_sb = _mock_sb()
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"token": "not-valid-fernet"}]
        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            with pytest.raises(UserStoreError, match="Failed to decrypt"):
                get_quercus_token("u1")


# ── delete_quercus_token ──────────────────────────────────────────────────────

class TestDeleteQuercusToken:
    def test_calls_delete_on_supabase(self):
        from auth.user_store import delete_quercus_token
        mock_sb = _mock_sb()

        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            delete_quercus_token("u1")

        mock_sb.table.return_value.delete.assert_called_once()

    def test_noop_on_empty_user_id(self):
        """Empty user_id → no Supabase call."""
        from auth.user_store import delete_quercus_token
        mock_sb = _mock_sb()

        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            delete_quercus_token("")

        mock_sb.table.assert_not_called()

    def test_noop_on_none_user_id(self):
        from auth.user_store import delete_quercus_token
        mock_sb = _mock_sb()

        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            delete_quercus_token(None)

        mock_sb.table.assert_not_called()

    def test_raises_user_store_error_on_exception(self):
        from auth.user_store import delete_quercus_token, UserStoreError
        mock_sb = _mock_sb()
        mock_sb.table.return_value.delete.return_value.eq.return_value \
            .execute.side_effect = Exception("DB error")

        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            with pytest.raises(UserStoreError, match="Failed to delete"):
                delete_quercus_token("u1")


class TestUserStoreHelpers:
    def test_secret_or_env_reads_value(self, monkeypatch):
        from auth.user_store import _secret_or_env
        monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
        assert _secret_or_env("SUPABASE_URL") == "https://example.supabase.co"

    def test_get_supabase_client_requires_config(self, monkeypatch):
        from auth.user_store import get_supabase_client, UserStoreError
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_KEY", raising=False)
        with pytest.raises(UserStoreError, match="SUPABASE_URL and SUPABASE_KEY must be configured"):
            get_supabase_client()

    def test_get_supabase_client_uses_create_client(self, monkeypatch):
        from auth.user_store import get_supabase_client
        fake = object()
        monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "anon-key")
        with patch("auth.user_store.create_client", return_value=fake) as mock_create:
            result = get_supabase_client()
        assert result is fake
        mock_create.assert_called_once_with("https://example.supabase.co", "anon-key")


class TestGetOrCreateUserAdditional:
    def test_raises_when_lookup_after_upsert_returns_no_rows(self):
        from auth.user_store import get_or_create_user, UserStoreError
        mock_sb = _mock_sb()
        mock_sb.table.return_value.upsert.return_value.execute.return_value.data = []
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            with pytest.raises(UserStoreError, match="Supabase returned no user row after upsert"):
                get_or_create_user("g3", "none@example.com")


class TestSaveQuercusTokenAdditional:
    def test_raises_when_existing_token_check_fails(self):
        from auth.user_store import save_quercus_token, UserStoreError
        mock_sb = _mock_sb()
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = Exception("check failed")
        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            with pytest.raises(UserStoreError, match="Failed to check existing Quercus token"):
                save_quercus_token("u1", "tok")

    def test_raises_when_insert_fails(self):
        from auth.user_store import save_quercus_token, UserStoreError
        mock_sb = _mock_sb()
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        mock_sb.table.return_value.insert.return_value.execute.side_effect = Exception("insert failed")
        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            with pytest.raises(UserStoreError, match="Failed to save Quercus token"):
                save_quercus_token("u1", "tok")


class TestGetQuercusTokenAdditional:
    def test_raises_when_load_fails(self):
        from auth.user_store import get_quercus_token, UserStoreError
        mock_sb = _mock_sb()
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = Exception("load failed")
        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            with pytest.raises(UserStoreError, match="Failed to load Quercus token"):
                get_quercus_token("u1")

    def test_returns_none_when_encrypted_value_is_blank(self):
        from auth.user_store import get_quercus_token
        mock_sb = _mock_sb()
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"token": ""}]
        with patch("auth.user_store.get_supabase_client", return_value=mock_sb):
            assert get_quercus_token("u1") is None
