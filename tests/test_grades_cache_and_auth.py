"""
tests/test_grades_cache_and_auth.py — tests for:
  - integrations/grades_cache.py
  - api/services/auth_service.py

All Supabase and HTTP calls are mocked.
"""

import pytest
from unittest.mock import MagicMock, patch


def _mock_sb():
    m = MagicMock()
    chain = m.table.return_value
    for attr in ("select", "insert", "upsert", "update", "delete", "eq",
                 "order", "limit", "execute"):
        getattr(chain, attr).return_value = chain
    chain.execute.return_value = MagicMock(data=[])
    return m


# ── pure helpers ──────────────────────────────────────────────────────────────

class TestToFloat:
    def test_none_returns_none(self):
        from integrations.grades_cache import _to_float
        assert _to_float(None) is None

    def test_decimal_converts(self):
        from integrations.grades_cache import _to_float
        from decimal import Decimal
        assert _to_float(Decimal("3.14")) == pytest.approx(3.14)

    def test_int_converts(self):
        from integrations.grades_cache import _to_float
        assert _to_float(80) == 80.0


class TestFallbackComponentKey:
    def test_builds_key_from_fields(self):
        from integrations.grades_cache import _fallback_component_key
        comp = {"source": "canvas", "group_name": "Midterm", "name": "MT1",
                "status": "graded", "possible": 100}
        key = _fallback_component_key(comp)
        assert "canvas" in key
        assert "midterm" in key

    def test_missing_fields_use_defaults(self):
        from integrations.grades_cache import _fallback_component_key
        key = _fallback_component_key({})
        assert key  # should not be empty


class TestNormaliseComponent:
    def test_raises_on_empty_name(self):
        from integrations.grades_cache import _normalise_component, GradesCacheError
        with pytest.raises(GradesCacheError, match="name"):
            _normalise_component({"name": "", "component_key": "k1"})

    def test_returns_normalised_dict(self):
        from integrations.grades_cache import _normalise_component
        result = _normalise_component({
            "component_key": "midterm",
            "name": "Midterm",
            "earned": 80.0,
            "possible": 100.0,
        })
        assert result["component_key"] == "midterm"
        assert result["score"] == 80.0

    def test_falls_back_to_computed_key_when_missing(self):
        from integrations.grades_cache import _normalise_component
        result = _normalise_component({"name": "Quiz", "source": "canvas",
                                       "group_name": "Quizzes", "status": "graded"})
        assert result["component_key"]  # computed, non-empty


# ── get_saved_grades ──────────────────────────────────────────────────────────

class TestGetSavedGrades:
    def test_returns_empty_for_blank_user(self):
        from integrations.grades_cache import get_saved_grades
        assert get_saved_grades("", 1001) == {}
        assert get_saved_grades(None, 1001) == {}

    def test_returns_rows_keyed_by_component_key(self):
        from integrations.grades_cache import get_saved_grades
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[{
            "component_key": "midterm",
            "component_name": "Midterm",
            "score": 80.0,
            "possible": 100.0,
            "acknowledged_at": None,
            "saved_at": None,
        }])
        with patch("integrations.grades_cache._get_supabase_client", return_value=mock_sb):
            result = get_saved_grades("u1", 1001)
        assert "midterm" in result
        assert result["midterm"]["score"] == 80.0

    def test_raises_on_db_error(self):
        from integrations.grades_cache import get_saved_grades, GradesCacheError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("integrations.grades_cache._get_supabase_client", return_value=mock_sb):
            with pytest.raises(GradesCacheError):
                get_saved_grades("u1", 1001)


# ── get_grade_overrides ───────────────────────────────────────────────────────

class TestGetGradeOverrides:
    def test_returns_empty_for_blank_user(self):
        from integrations.grades_cache import get_grade_overrides
        assert get_grade_overrides("", 1001) == {}

    def test_returns_override_keyed_by_component_key(self):
        from integrations.grades_cache import get_grade_overrides
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[{
            "component_key": "final",
            "manual_score": 90.0,
            "manual_possible": 100.0,
            "created_at": None,
        }])
        with patch("integrations.grades_cache._get_supabase_client", return_value=mock_sb):
            result = get_grade_overrides("u1", 1001)
        assert "final" in result
        assert result["final"]["manual_score"] == 90.0

    def test_raises_on_db_error(self):
        from integrations.grades_cache import get_grade_overrides, GradesCacheError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("integrations.grades_cache._get_supabase_client", return_value=mock_sb):
            with pytest.raises(GradesCacheError):
                get_grade_overrides("u1", 1001)


# ── detect_new_grades ─────────────────────────────────────────────────────────

class TestDetectNewGrades:
    def test_detects_new_component(self):
        from integrations.grades_cache import detect_new_grades
        live = [{"component_key": "midterm", "name": "Midterm",
                 "status": "graded", "earned": 80.0, "possible": 100.0}]
        with patch("integrations.grades_cache.get_saved_grades", return_value={}):
            result = detect_new_grades("u1", 1001, live)
        assert "midterm" in result

    def test_detects_changed_score(self):
        from integrations.grades_cache import detect_new_grades
        live = [{"component_key": "midterm", "name": "Midterm",
                 "status": "graded", "earned": 85.0, "possible": 100.0}]
        saved = {"midterm": {"score": 75.0, "possible": 100.0, "component_name": "Midterm"}}
        with patch("integrations.grades_cache.get_saved_grades", return_value=saved):
            result = detect_new_grades("u1", 1001, live)
        assert "midterm" in result

    def test_skips_ungraded_components(self):
        from integrations.grades_cache import detect_new_grades
        live = [{"component_key": "final", "name": "Final", "status": "ungraded"}]
        with patch("integrations.grades_cache.get_saved_grades", return_value={}):
            result = detect_new_grades("u1", 1001, live)
        assert result == []

    def test_no_change_returns_empty(self):
        from integrations.grades_cache import detect_new_grades
        live = [{"component_key": "midterm", "name": "Midterm",
                 "status": "graded", "earned": 80.0, "possible": 100.0}]
        saved = {"midterm": {"score": 80.0, "possible": 100.0, "component_name": "Midterm"}}
        with patch("integrations.grades_cache.get_saved_grades", return_value=saved):
            result = detect_new_grades("u1", 1001, live)
        assert result == []


# ── save_grades ───────────────────────────────────────────────────────────────

class TestSaveGrades:
    def test_skips_when_no_graded_components(self):
        from integrations.grades_cache import save_grades
        with patch("integrations.grades_cache._get_supabase_client") as mock_fn:
            save_grades("u1", 1001, [{"status": "ungraded", "name": "Quiz"}])
            mock_fn.assert_not_called()

    def test_raises_for_blank_user_id(self):
        from integrations.grades_cache import save_grades, GradesCacheError
        with pytest.raises(GradesCacheError):
            save_grades("", 1001, [])

    def test_upserts_graded_rows(self):
        from integrations.grades_cache import save_grades
        mock_sb = _mock_sb()
        components = [{"component_key": "mid", "name": "Midterm",
                       "status": "graded", "earned": 80.0, "possible": 100.0}]
        with patch("integrations.grades_cache._get_supabase_client", return_value=mock_sb):
            save_grades("u1", 1001, components)
        mock_sb.table.return_value.upsert.assert_called_once()

    def test_raises_on_db_error(self):
        from integrations.grades_cache import save_grades, GradesCacheError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        components = [{"component_key": "mid", "name": "Midterm",
                       "status": "graded", "earned": 80.0, "possible": 100.0}]
        with patch("integrations.grades_cache._get_supabase_client", return_value=mock_sb):
            with pytest.raises(GradesCacheError):
                save_grades("u1", 1001, components)


# ── save_grade_override ───────────────────────────────────────────────────────

class TestSaveGradeOverride:
    def test_raises_for_blank_user_id(self):
        from integrations.grades_cache import save_grade_override, GradesCacheError
        with pytest.raises(GradesCacheError):
            save_grade_override("", 1001, "midterm", 80.0, 100.0)

    def test_raises_for_blank_component_key(self):
        from integrations.grades_cache import save_grade_override, GradesCacheError
        with pytest.raises(GradesCacheError):
            save_grade_override("u1", 1001, "", 80.0, 100.0)

    def test_upserts_override(self):
        from integrations.grades_cache import save_grade_override
        mock_sb = _mock_sb()
        with patch("integrations.grades_cache._get_supabase_client", return_value=mock_sb):
            save_grade_override("u1", 1001, "midterm", 80.0, 100.0)
        mock_sb.table.return_value.upsert.assert_called_once()


# ── delete_grade_override ─────────────────────────────────────────────────────

class TestDeleteGradeOverride:
    def test_raises_for_blank_user_id(self):
        from integrations.grades_cache import delete_grade_override, GradesCacheError
        with pytest.raises(GradesCacheError):
            delete_grade_override("", 1001, "midterm")

    def test_raises_for_blank_component_key(self):
        from integrations.grades_cache import delete_grade_override, GradesCacheError
        with pytest.raises(GradesCacheError):
            delete_grade_override("u1", 1001, "")

    def test_calls_delete(self):
        from integrations.grades_cache import delete_grade_override
        mock_sb = _mock_sb()
        with patch("integrations.grades_cache._get_supabase_client", return_value=mock_sb):
            delete_grade_override("u1", 1001, "midterm")
        mock_sb.table.return_value.delete.assert_called()

    def test_raises_on_db_error(self):
        from integrations.grades_cache import delete_grade_override, GradesCacheError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("integrations.grades_cache._get_supabase_client", return_value=mock_sb):
            with pytest.raises(GradesCacheError):
                delete_grade_override("u1", 1001, "midterm")


# ── auth_service ──────────────────────────────────────────────────────────────

class TestBuildGoogleOauthUrl:
    def test_includes_client_id_and_redirect(self):
        from api.services.auth_service import build_google_oauth_url
        url = build_google_oauth_url("http://localhost/callback")
        assert "accounts.google.com" in url
        assert "client_id" in url
        assert "redirect_uri" in url


class TestCreateAndDecodeAccessToken:
    def test_roundtrip(self):
        from api.services.auth_service import create_access_token, decode_access_token
        user = {"id": "u1", "email": "a@b.com", "name": "Alice", "google_id": "g1"}
        token = create_access_token(user)
        payload = decode_access_token(token)
        assert payload["user_id"] == "u1"
        assert payload["email"] == "a@b.com"

    def test_decode_raises_on_invalid_token(self):
        from api.services.auth_service import decode_access_token, AuthServiceError
        with pytest.raises(AuthServiceError):
            decode_access_token("not.a.valid.token")


class TestExchangeGoogleCode:
    def test_returns_userinfo_on_success(self):
        from api.services.auth_service import exchange_google_code
        token_resp = MagicMock(ok=True)
        token_resp.json.return_value = {"access_token": "tok-123"}
        userinfo_resp = MagicMock(ok=True)
        userinfo_resp.json.return_value = {"sub": "g1", "email": "a@b.com", "name": "Alice"}

        with patch("api.services.auth_service.requests.post", return_value=token_resp), \
             patch("api.services.auth_service.requests.get", return_value=userinfo_resp):
            result = exchange_google_code("code-abc", "http://localhost/callback")

        assert result["sub"] == "g1"

    def test_raises_on_bad_token_response(self):
        from api.services.auth_service import exchange_google_code, AuthServiceError
        bad_resp = MagicMock(ok=False, status_code=400, text="error")
        with patch("api.services.auth_service.requests.post", return_value=bad_resp):
            with pytest.raises(AuthServiceError):
                exchange_google_code("bad-code", "http://localhost/callback")

    def test_raises_when_no_access_token(self):
        from api.services.auth_service import exchange_google_code, AuthServiceError
        token_resp = MagicMock(ok=True)
        token_resp.json.return_value = {}  # no access_token
        with patch("api.services.auth_service.requests.post", return_value=token_resp):
            with pytest.raises(AuthServiceError, match="access_token"):
                exchange_google_code("code", "http://localhost/callback")

    def test_raises_on_bad_userinfo_response(self):
        from api.services.auth_service import exchange_google_code, AuthServiceError
        token_resp = MagicMock(ok=True)
        token_resp.json.return_value = {"access_token": "tok"}
        bad_userinfo = MagicMock(ok=False, status_code=401, text="Unauthorized")

        with patch("api.services.auth_service.requests.post", return_value=token_resp), \
             patch("api.services.auth_service.requests.get", return_value=bad_userinfo):
            with pytest.raises(AuthServiceError):
                exchange_google_code("code", "http://localhost/callback")


class TestGetOrCreateBackendUser:
    def test_returns_user_with_name(self):
        from api.services.auth_service import get_or_create_backend_user
        fake_user = {"id": "u1", "email": "a@b.com", "google_id": "g1"}
        with patch("api.services.auth_service.get_or_create_user", return_value=fake_user):
            result = get_or_create_backend_user({"sub": "g1", "email": "a@b.com", "name": "Alice"})
        assert result["name"] == "Alice"

    def test_raises_when_no_sub(self):
        from api.services.auth_service import get_or_create_backend_user, AuthServiceError
        with pytest.raises(AuthServiceError, match="subject"):
            get_or_create_backend_user({"email": "a@b.com"})


# ── _required_env (auth_service) ─────────────────────────────────────────────

class TestRequiredEnv:
    def test_raises_when_env_var_not_set(self):
        from api.services.auth_service import _required_env, AuthServiceError
        with patch("api.services.auth_service.os.getenv", return_value=None):
            with pytest.raises(AuthServiceError, match="must be configured"):
                _required_env("SOME_MISSING_VAR")

    def test_returns_value_when_set(self):
        from api.services.auth_service import _required_env
        with patch("api.services.auth_service.os.getenv", return_value="my-secret"):
            result = _required_env("JWT_SECRET")
        assert result == "my-secret"


# ── exchange_google_code — no sub in userinfo (line 78) ───────────────────────

class TestExchangeGoogleCodeNoSub:
    def test_raises_when_userinfo_has_no_sub(self):
        from api.services.auth_service import exchange_google_code, AuthServiceError
        token_resp = MagicMock(ok=True)
        token_resp.json.return_value = {"access_token": "tok-abc"}
        userinfo_resp = MagicMock(ok=True)
        userinfo_resp.json.return_value = {"email": "a@b.com"}  # no "sub"

        with patch("api.services.auth_service.requests.post", return_value=token_resp), \
             patch("api.services.auth_service.requests.get", return_value=userinfo_resp):
            with pytest.raises(AuthServiceError, match="subject identifier"):
                exchange_google_code("code-xyz", "http://localhost/callback")


# ── grades_cache — _secret_or_env and _get_supabase_client ──────────────────

class TestGradesCacheSupabaseClient:
    def test_secret_or_env_returns_none_for_missing_var(self):
        from integrations.grades_cache import _secret_or_env
        with patch("integrations.grades_cache.os.getenv", return_value=None):
            assert _secret_or_env("MISSING_VAR") is None

    def test_secret_or_env_returns_value_for_present_var(self):
        from integrations.grades_cache import _secret_or_env
        with patch("integrations.grades_cache.os.getenv", return_value="my-url"):
            assert _secret_or_env("SUPABASE_URL") == "my-url"

    def test_get_supabase_client_raises_when_url_missing(self):
        from integrations.grades_cache import _get_supabase_client, GradesCacheError
        with patch("integrations.grades_cache._secret_or_env", return_value=None):
            with pytest.raises(GradesCacheError, match="SUPABASE_URL"):
                _get_supabase_client()

    def test_get_supabase_client_returns_client_when_configured(self):
        from integrations.grades_cache import _get_supabase_client
        mock_client = MagicMock()

        def fake_env(name):
            return {"SUPABASE_URL": "https://fake.supabase.co", "SUPABASE_KEY": "key"}[name]

        with patch("integrations.grades_cache._secret_or_env", side_effect=fake_env), \
             patch("integrations.grades_cache.create_client", return_value=mock_client):
            result = _get_supabase_client()
        assert result is mock_client


# ── save_grade_override — DB error path (lines 217-218) ──────────────────────

class TestSaveGradeOverrideDbError:
    def test_raises_on_db_error(self):
        from integrations.grades_cache import save_grade_override, GradesCacheError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("integrations.grades_cache._get_supabase_client", return_value=mock_sb):
            with pytest.raises(GradesCacheError, match="Failed to save grade override"):
                save_grade_override("u1", 1001, "midterm", 80.0, 100.0)


# ── api/dependencies.py — invalid token payload (line 30) ────────────────────

class TestGetCurrentUser:
    def test_raises_401_on_auth_service_error(self):
        from api.dependencies import get_current_user
        from api.services.auth_service import AuthServiceError
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        creds = MagicMock(spec=HTTPAuthorizationCredentials)
        creds.credentials = "bad-token"

        with patch("api.dependencies.decode_access_token", side_effect=AuthServiceError("bad")):
            with pytest.raises(HTTPException) as exc:
                get_current_user(creds)
        assert exc.value.status_code == 401

    def test_raises_401_when_user_id_missing(self):
        from api.dependencies import get_current_user
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        creds = MagicMock(spec=HTTPAuthorizationCredentials)
        creds.credentials = "tok"

        with patch("api.dependencies.decode_access_token", return_value={"google_id": "g1"}):
            with pytest.raises(HTTPException) as exc:
                get_current_user(creds)
        assert exc.value.status_code == 401
        assert "Invalid token payload" in exc.value.detail

    def test_raises_401_when_google_id_missing(self):
        from api.dependencies import get_current_user
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        creds = MagicMock(spec=HTTPAuthorizationCredentials)
        creds.credentials = "tok"

        with patch("api.dependencies.decode_access_token", return_value={"user_id": "u1"}):
            with pytest.raises(HTTPException) as exc:
                get_current_user(creds)
        assert exc.value.status_code == 401

    def test_returns_user_dict_on_success(self):
        from api.dependencies import get_current_user
        from fastapi.security import HTTPAuthorizationCredentials

        creds = MagicMock(spec=HTTPAuthorizationCredentials)
        creds.credentials = "tok"
        payload = {"user_id": "u1", "google_id": "g1", "email": "a@b.com", "name": "Alice"}

        with patch("api.dependencies.decode_access_token", return_value=payload):
            result = get_current_user(creds)
        assert result["user_id"] == "u1"
        assert result["google_id"] == "g1"


# ── api/services/grade_snapshot_cache.py — _is_fresh (line 19) ───────────────

class TestIsFreshGradeSnapshot:
    def test_returns_false_when_cached_at_not_datetime(self):
        from api.services.grade_snapshot_cache import _is_fresh
        entry = {"cached_at": "2024-01-01T00:00:00Z", "data": {}}
        assert _is_fresh(entry) is False

    def test_returns_false_when_entry_is_none(self):
        from api.services.grade_snapshot_cache import _is_fresh
        assert _is_fresh(None) is False

    def test_returns_false_when_entry_is_empty(self):
        from api.services.grade_snapshot_cache import _is_fresh
        assert _is_fresh({}) is False

    def test_returns_true_when_fresh(self):
        from api.services.grade_snapshot_cache import _is_fresh
        from datetime import datetime, timezone
        entry = {"cached_at": datetime.now(timezone.utc), "data": {}}
        assert _is_fresh(entry) is True
