"""
tests/test_encryption_and_syllabus_cache.py — tests for:
  - integrations/encryption.py
  - integrations/syllabus_cache.py

All Supabase and cipher calls are mocked or use a known valid key.
"""

import base64
import pytest
from unittest.mock import MagicMock, patch

# A known valid Fernet key (32 zero bytes, base64-urlsafe encoded).
_VALID_KEY = base64.urlsafe_b64encode(b"\x00" * 32).decode()


def _mock_sb():
    m = MagicMock()
    chain = m.table.return_value
    for attr in ("select", "insert", "upsert", "update", "delete", "eq",
                 "order", "limit", "execute"):
        getattr(chain, attr).return_value = chain
    chain.execute.return_value = MagicMock(data=[])
    return m


# ── encryption.py ──────────────────────────────────────────────────────────────

class TestEncryptionImportFailureHandler:
    def test_module_raises_on_fernet_import_failure(self):
        """Cover the except block in encryption.py that handles a failed cryptography import."""
        import sys
        import importlib
        real_mod = sys.modules.pop("api.integrations.encryption", None)
        try:
            with patch.dict(sys.modules, {"cryptography.fernet": None}), \
                 patch("builtins.print"), \
                 patch("traceback.print_exc"):
                with pytest.raises(ImportError):
                    importlib.import_module("api.integrations.encryption")
        finally:
            sys.modules.pop("api.integrations.encryption", None)
            if real_mod is not None:
                sys.modules["api.integrations.encryption"] = real_mod


class TestGetCipher:
    def test_raises_when_key_not_set(self):
        from api.integrations.encryption import _get_cipher, EncryptionError
        with patch("api.integrations.encryption.os.getenv", return_value=None):
            with pytest.raises(EncryptionError, match="ENCRYPTION_KEY is not set"):
                _get_cipher()

    def test_raises_on_invalid_key(self):
        from api.integrations.encryption import _get_cipher, EncryptionError
        with patch("api.integrations.encryption.os.getenv", return_value="not-a-valid-fernet-key!"):
            with pytest.raises(EncryptionError, match="ENCRYPTION_KEY is invalid"):
                _get_cipher()

    def test_returns_cipher_with_valid_key(self):
        from api.integrations.encryption import _get_cipher
        from cryptography.fernet import Fernet
        with patch("api.integrations.encryption.os.getenv", return_value=_VALID_KEY):
            cipher = _get_cipher()
        assert isinstance(cipher, Fernet)


class TestEncryptToken:
    def test_raises_on_empty_string(self):
        from api.integrations.encryption import encrypt_token, EncryptionError
        with pytest.raises(EncryptionError, match="non-empty"):
            encrypt_token("")

    def test_raises_on_non_string(self):
        from api.integrations.encryption import encrypt_token, EncryptionError
        with pytest.raises(EncryptionError, match="non-empty"):
            encrypt_token(None)

    def test_returns_non_empty_string(self):
        from api.integrations.encryption import encrypt_token
        with patch("api.integrations.encryption.os.getenv", return_value=_VALID_KEY):
            result = encrypt_token("my-secret-token")
        assert isinstance(result, str)
        assert len(result) > 0
        assert result != "my-secret-token"


class TestDecryptToken:
    def test_raises_on_empty_string(self):
        from api.integrations.encryption import decrypt_token, EncryptionError
        with pytest.raises(EncryptionError, match="non-empty"):
            decrypt_token("")

    def test_raises_on_non_string(self):
        from api.integrations.encryption import decrypt_token, EncryptionError
        with pytest.raises(EncryptionError, match="non-empty"):
            decrypt_token(None)

    def test_roundtrip_encrypt_decrypt(self):
        from api.integrations.encryption import encrypt_token, decrypt_token
        original = "quercus-access-token-abc123"
        with patch("api.integrations.encryption.os.getenv", return_value=_VALID_KEY):
            encrypted = encrypt_token(original)
            recovered = decrypt_token(encrypted)
        assert recovered == original

    def test_corrupted_token_raises(self):
        from api.integrations.encryption import decrypt_token
        with patch("api.integrations.encryption.os.getenv", return_value=_VALID_KEY):
            with pytest.raises(Exception):
                decrypt_token("this-is-not-a-valid-fernet-token")


# ── syllabus_cache.py ──────────────────────────────────────────────────────────

class TestGetSyllabusCacheClient:
    def test_raises_when_url_and_key_missing(self):
        from api.integrations.syllabus_cache import _get_supabase_client, SyllabusCacheError
        with patch("api.integrations.syllabus_cache._secret_or_env", return_value=None):
            with pytest.raises(SyllabusCacheError, match="SUPABASE_URL"):
                _get_supabase_client()

    def test_raises_when_only_key_missing(self):
        from api.integrations.syllabus_cache import _get_supabase_client, SyllabusCacheError
        def _fake_env(name):
            return "https://fake.supabase.co" if name == "SUPABASE_URL" else None
        with patch("api.integrations.syllabus_cache._secret_or_env", side_effect=_fake_env):
            with pytest.raises(SyllabusCacheError, match="SUPABASE_KEY"):
                _get_supabase_client()

    def test_returns_client_when_credentials_set(self):
        from api.integrations.syllabus_cache import _get_supabase_client
        mock_client = MagicMock()
        with patch("api.integrations.syllabus_cache.create_client", return_value=mock_client):
            result = _get_supabase_client()
        assert result is mock_client


class TestSecretOrEnv:
    def test_returns_env_var_value(self):
        from api.integrations.syllabus_cache import _secret_or_env
        # SUPABASE_URL is set in os.environ via the real .env file
        with patch("os.getenv", return_value="test-value") as mock_getenv:
            result = _secret_or_env("SUPABASE_URL")
        assert result == "test-value"

    def test_returns_none_for_missing_var(self):
        from api.integrations.syllabus_cache import _secret_or_env
        with patch("os.getenv", return_value=None):
            result = _secret_or_env("NONEXISTENT_VAR")
        assert result is None


class TestGetCachedSyllabusWeights:
    def test_returns_weights_on_cache_hit(self):
        from api.integrations.syllabus_cache import get_cached_syllabus_weights
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(
            data=[{"weights": {"Midterm": 40.0, "Final": 60.0}}]
        )
        with patch("api.integrations.syllabus_cache._get_supabase_client", return_value=mock_sb):
            result = get_cached_syllabus_weights(1001, "syllabus.pdf")
        assert result == {"Midterm": 40.0, "Final": 60.0}

    def test_returns_none_on_cache_miss(self):
        from api.integrations.syllabus_cache import get_cached_syllabus_weights
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[])
        with patch("api.integrations.syllabus_cache._get_supabase_client", return_value=mock_sb):
            result = get_cached_syllabus_weights(1001, "syllabus.pdf")
        assert result is None

    def test_returns_none_when_weights_not_dict(self):
        from api.integrations.syllabus_cache import get_cached_syllabus_weights
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(
            data=[{"weights": "not-a-dict"}]
        )
        with patch("api.integrations.syllabus_cache._get_supabase_client", return_value=mock_sb):
            result = get_cached_syllabus_weights(1001, "syllabus.pdf")
        assert result is None

    def test_raises_on_db_error(self):
        from api.integrations.syllabus_cache import get_cached_syllabus_weights, SyllabusCacheError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.integrations.syllabus_cache._get_supabase_client", return_value=mock_sb):
            with pytest.raises(SyllabusCacheError, match="Failed to load cached"):
                get_cached_syllabus_weights(1001, "syllabus.pdf")


class TestSaveCachedSyllabusWeights:
    def test_inserts_when_no_existing_row(self):
        from api.integrations.syllabus_cache import save_cached_syllabus_weights
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.side_effect = [
            MagicMock(data=[]),   # existing check: no rows
            MagicMock(data=[]),   # insert
        ]
        with patch("api.integrations.syllabus_cache._get_supabase_client", return_value=mock_sb):
            save_cached_syllabus_weights(1001, "syllabus.pdf", {"Midterm": 40.0})
        mock_sb.table.return_value.insert.assert_called()

    def test_updates_when_existing_row_found(self):
        from api.integrations.syllabus_cache import save_cached_syllabus_weights
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "cache-row-1"}]),  # existing check: row found
            MagicMock(data=[]),                        # update
        ]
        with patch("api.integrations.syllabus_cache._get_supabase_client", return_value=mock_sb):
            save_cached_syllabus_weights(1001, "syllabus.pdf", {"Midterm": 40.0})
        mock_sb.table.return_value.update.assert_called()

    def test_raises_on_db_check_error(self):
        from api.integrations.syllabus_cache import save_cached_syllabus_weights, SyllabusCacheError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.integrations.syllabus_cache._get_supabase_client", return_value=mock_sb):
            with pytest.raises(SyllabusCacheError, match="Failed to check cached"):
                save_cached_syllabus_weights(1001, "syllabus.pdf", {"Midterm": 40.0})

    def test_raises_on_save_error(self):
        from api.integrations.syllabus_cache import save_cached_syllabus_weights, SyllabusCacheError
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.side_effect = [
            MagicMock(data=[]),          # existing check: no rows
            Exception("insert failed"),  # insert raises
        ]
        with patch("api.integrations.syllabus_cache._get_supabase_client", return_value=mock_sb):
            with pytest.raises(SyllabusCacheError, match="Failed to save cached"):
                save_cached_syllabus_weights(1001, "syllabus.pdf", {"Midterm": 40.0})
