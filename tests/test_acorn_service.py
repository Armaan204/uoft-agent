"""
tests/test_acorn_service.py — tests for api/services/acorn_service.py

All Supabase calls are mocked.
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


# ── _get_supabase ──────────────────────────────────────────────────────────────

class TestGetSupabase:
    def test_raises_when_url_and_key_missing(self):
        from api.services.acorn_service import _get_supabase, AcornServiceError
        with patch("api.services.acorn_service.os.getenv", return_value=None):
            with pytest.raises(AcornServiceError, match="SUPABASE_URL"):
                _get_supabase()

    def test_raises_when_key_missing(self):
        from api.services.acorn_service import _get_supabase, AcornServiceError
        def _getenv(key, *args):
            return "https://fake.supabase.co" if key == "SUPABASE_URL" else None
        with patch("api.services.acorn_service.os.getenv", side_effect=_getenv):
            with pytest.raises(AcornServiceError, match="SUPABASE_KEY"):
                _get_supabase()

    def test_returns_client_when_credentials_set(self):
        from api.services.acorn_service import _get_supabase
        mock_client = MagicMock()
        with patch("api.services.acorn_service.create_client", return_value=mock_client):
            result = _get_supabase()
        assert result is mock_client


# ── import_acorn_data ──────────────────────────────────────────────────────────

class TestImportAcornData:
    def test_success_returns_validated(self):
        from api.services.acorn_service import import_acorn_data
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[{"id": "row-1"}])
        payload = {"courses": [], "importedAt": "2024-01-01T00:00:00+00:00"}
        with patch("api.services.acorn_service._get_supabase", return_value=mock_sb):
            result = import_acorn_data("ABC123", payload)
        assert result["importCode"] == "ABC123"

    def test_raises_on_missing_import_code(self):
        from api.services.acorn_service import import_acorn_data
        from api.integrations.acorn_store import AcornStoreError
        with pytest.raises(AcornStoreError):
            import_acorn_data("", {"courses": []})

    def test_raises_when_supabase_returns_no_rows(self):
        from api.services.acorn_service import import_acorn_data, AcornServiceError
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[])
        payload = {"courses": [], "importedAt": "2024-01-01T00:00:00+00:00"}
        with patch("api.services.acorn_service._get_supabase", return_value=mock_sb):
            with pytest.raises(AcornServiceError, match="no inserted"):
                import_acorn_data("ABC123", payload)

    def test_raises_on_supabase_exception(self):
        from api.services.acorn_service import import_acorn_data, AcornServiceError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        payload = {"courses": [], "importedAt": "2024-01-01T00:00:00+00:00"}
        with patch("api.services.acorn_service._get_supabase", return_value=mock_sb):
            with pytest.raises(AcornServiceError, match="Failed to store"):
                import_acorn_data("ABC123", payload)


# ── get_latest_import ──────────────────────────────────────────────────────────

class TestGetLatestImport:
    def test_returns_data_for_code(self):
        from api.services.acorn_service import get_latest_import
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(
            data=[{"data": {"importCode": "ABC123", "courses": []}}]
        )
        with patch("api.services.acorn_service._get_supabase", return_value=mock_sb):
            result = get_latest_import("ABC123")
        assert result is not None
        assert result["importCode"] == "ABC123"

    def test_returns_none_when_no_rows(self):
        from api.services.acorn_service import get_latest_import
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[])
        with patch("api.services.acorn_service._get_supabase", return_value=mock_sb):
            result = get_latest_import("ABC123")
        assert result is None

    def test_raises_on_db_error(self):
        from api.services.acorn_service import get_latest_import, AcornServiceError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.services.acorn_service._get_supabase", return_value=mock_sb):
            with pytest.raises(AcornServiceError, match="Failed to load latest"):
                get_latest_import("ABC123")


# ── get_import_status ──────────────────────────────────────────────────────────

class TestGetImportStatus:
    def test_returns_exists_true_with_data(self):
        from api.services.acorn_service import get_import_status
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[{
            "data": {
                "importCode": "ABC123",
                "importedAt": "2024-01-01T00:00:00+00:00",
                "courses": [{"courseCode": "CSCA08H3"}],
            }
        }])
        with patch("api.services.acorn_service._get_supabase", return_value=mock_sb):
            result = get_import_status("ABC123")
        assert result["exists"] is True
        assert result["courseCount"] == 1

    def test_returns_exists_false_when_no_rows(self):
        from api.services.acorn_service import get_import_status
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[])
        with patch("api.services.acorn_service._get_supabase", return_value=mock_sb):
            result = get_import_status("ABC123")
        assert result["exists"] is False
        assert result["importedAt"] is None

    def test_raises_on_db_error(self):
        from api.services.acorn_service import get_import_status, AcornServiceError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.services.acorn_service._get_supabase", return_value=mock_sb):
            with pytest.raises(AcornServiceError, match="Failed to load ACORN import status"):
                get_import_status("ABC123")


# ── get_latest_import_for_user ─────────────────────────────────────────────────

class TestGetLatestImportForUser:
    def test_returns_none_for_blank_user_id(self):
        from api.services.acorn_service import get_latest_import_for_user
        assert get_latest_import_for_user("") is None
        assert get_latest_import_for_user(None) is None

    def test_returns_data_when_row_found(self):
        from api.services.acorn_service import get_latest_import_for_user
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[{
            "id": "row-1",
            "data": {"importCode": "ABC", "courses": []},
            "imported_at": "2024-01-01T00:00:00+00:00",
        }])
        with patch("api.services.acorn_service.get_supabase_client", return_value=mock_sb):
            result = get_latest_import_for_user("u1")
        assert result is not None
        assert result["importedAt"] == "2024-01-01T00:00:00+00:00"

    def test_returns_none_when_no_rows(self):
        from api.services.acorn_service import get_latest_import_for_user
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[])
        with patch("api.services.acorn_service.get_supabase_client", return_value=mock_sb):
            result = get_latest_import_for_user("u1")
        assert result is None

    def test_raises_on_db_error(self):
        from api.services.acorn_service import get_latest_import_for_user, AcornServiceError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.services.acorn_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(AcornServiceError, match="Failed to load saved"):
                get_latest_import_for_user("u1")


# ── _parse_credits ─────────────────────────────────────────────────────────────

class TestParseCredits:
    def test_none_returns_none(self):
        from api.services.acorn_service import _parse_credits
        assert _parse_credits(None) is None

    def test_zero_returns_none(self):
        from api.services.acorn_service import _parse_credits
        assert _parse_credits(0) is None

    def test_negative_returns_none(self):
        from api.services.acorn_service import _parse_credits
        assert _parse_credits(-0.5) is None

    def test_valid_returns_float(self):
        from api.services.acorn_service import _parse_credits
        assert _parse_credits("0.5") == 0.5

    def test_invalid_string_returns_none(self):
        from api.services.acorn_service import _parse_credits
        assert _parse_credits("invalid") is None


# ── _parse_mark ────────────────────────────────────────────────────────────────

class TestParseMark:
    def test_none_returns_none(self):
        from api.services.acorn_service import _parse_mark
        assert _parse_mark(None) is None

    def test_valid_returns_float(self):
        from api.services.acorn_service import _parse_mark
        assert _parse_mark("85") == 85.0

    def test_invalid_returns_none(self):
        from api.services.acorn_service import _parse_mark
        assert _parse_mark("A+") is None


# ── _is_earned_course ──────────────────────────────────────────────────────────

class TestIsEarnedCourse:
    def test_ipr_grade_not_earned(self):
        from api.services.acorn_service import _is_earned_course
        assert _is_earned_course({"grade": "IPR", "credits": "0.5"}) is False

    def test_nga_grade_not_earned(self):
        from api.services.acorn_service import _is_earned_course
        assert _is_earned_course({"grade": "NGA", "credits": "0.5"}) is False

    def test_lwd_grade_not_earned(self):
        from api.services.acorn_service import _is_earned_course
        assert _is_earned_course({"grade": "LWD", "credits": "0.5"}) is False

    def test_f_grade_not_earned(self):
        from api.services.acorn_service import _is_earned_course
        assert _is_earned_course({"grade": "F", "credits": "0.5"}) is False

    def test_low_mark_not_earned(self):
        from api.services.acorn_service import _is_earned_course
        assert _is_earned_course({"grade": "A", "mark": "40", "credits": "0.5"}) is False

    def test_earned_with_valid_data(self):
        from api.services.acorn_service import _is_earned_course
        assert _is_earned_course({"grade": "A", "mark": "85", "credits": "0.5"}) is True

    def test_no_credits_not_earned(self):
        from api.services.acorn_service import _is_earned_course
        assert _is_earned_course({"grade": "A", "mark": "85", "credits": None}) is False


# ── _should_deduplicate_course_code ───────────────────────────────────────────

class TestShouldDeduplicateCourseCode:
    def test_wildcard_code_not_deduplicated(self):
        from api.services.acorn_service import _should_deduplicate_course_code
        assert _should_deduplicate_course_code("CSCA***") is False

    def test_empty_code_not_deduplicated(self):
        from api.services.acorn_service import _should_deduplicate_course_code
        assert _should_deduplicate_course_code("") is False

    def test_regular_code_deduplicated(self):
        from api.services.acorn_service import _should_deduplicate_course_code
        assert _should_deduplicate_course_code("CSCA08H3") is True


# ── _calculate_earned_credits ──────────────────────────────────────────────────

class TestCalculateEarnedCredits:
    def test_sums_earned_credits(self):
        from api.services.acorn_service import _calculate_earned_credits
        courses = [
            {"courseCode": "CSCA08H3", "grade": "A", "mark": "85", "credits": "0.5"},
            {"courseCode": "MATA30H3", "grade": "B+", "mark": "78", "credits": "0.5"},
        ]
        result = _calculate_earned_credits(courses)
        assert result == 1.0

    def test_deduplicates_same_course_code(self):
        from api.services.acorn_service import _calculate_earned_credits
        courses = [
            {"courseCode": "CSCA08H3", "grade": "A", "mark": "85", "credits": "0.5"},
            {"courseCode": "CSCA08H3", "grade": "A", "mark": "90", "credits": "0.5"},
        ]
        result = _calculate_earned_credits(courses)
        assert result == 0.5

    def test_excludes_unearned_courses(self):
        from api.services.acorn_service import _calculate_earned_credits
        courses = [
            {"courseCode": "CSCA08H3", "grade": "IPR", "credits": "0.5"},
        ]
        result = _calculate_earned_credits(courses)
        assert result == 0.0

    def test_wildcard_code_not_deduplicated_on_accumulation(self):
        from api.services.acorn_service import _calculate_earned_credits
        courses = [
            {"courseCode": "CSCA***", "grade": "A", "mark": "85", "credits": "0.5"},
            {"courseCode": "CSCA***", "grade": "A", "mark": "85", "credits": "0.5"},
        ]
        result = _calculate_earned_credits(courses)
        assert result == 1.0

    def test_skips_missing_course_code(self):
        from api.services.acorn_service import _calculate_earned_credits
        courses = [
            {"grade": "A", "mark": "85", "credits": "0.5"},
        ]
        result = _calculate_earned_credits(courses)
        assert result == 0.0

    def test_skips_none_credits_after_earned_check(self):
        from api.services.acorn_service import _calculate_earned_credits
        courses = [{"courseCode": "CSCA08H3", "grade": "A", "mark": "85", "credits": "0.5"}]
        with patch("api.services.acorn_service._is_earned_course", return_value=True), \
             patch("api.services.acorn_service._parse_credits", return_value=None):
            result = _calculate_earned_credits(courses)
        assert result == 0.0


# ── get_academic_history ───────────────────────────────────────────────────────

class TestGetAcademicHistory:
    def test_returns_empty_when_no_import(self):
        from api.services.acorn_service import get_academic_history
        with patch("api.services.acorn_service.get_latest_import_for_user", return_value=None):
            result = get_academic_history("u1")
        assert result == {"terms": [], "credits_earned": 0.0}

    def test_returns_structured_history_with_terms(self):
        from api.services.acorn_service import get_academic_history
        data = {
            "importedAt": "2024-01-01T00:00:00+00:00",
            "terms": [{
                "term": "Fall 2023",
                "sessionalGpa": 3.5,
                "cumulativeGpa": 3.5,
                "courses": [{
                    "courseCode": "CSCA08H3",
                    "title": "Intro CS",
                    "grade": "A",
                    "mark": "85",
                    "credits": "0.5",
                    "courseAverage": None,
                }]
            }],
            "programs": [],
        }
        with patch("api.services.acorn_service.get_latest_import_for_user", return_value=data):
            result = get_academic_history("u1")
        assert len(result["terms"]) == 1
        assert result["terms"][0]["term"] == "Fall 2023"
        assert "credits_earned" in result

    def test_handles_no_terms_key(self):
        from api.services.acorn_service import get_academic_history
        data = {"importedAt": "2024-01-01T00:00:00+00:00"}
        with patch("api.services.acorn_service.get_latest_import_for_user", return_value=data):
            result = get_academic_history("u1")
        assert result["terms"] == []

    def test_sorts_graded_courses_by_mark(self):
        from api.services.acorn_service import get_academic_history
        data = {
            "importedAt": "2024-01-01T00:00:00+00:00",
            "terms": [{
                "term": "Fall 2023",
                "sessionalGpa": 3.5,
                "cumulativeGpa": 3.5,
                "courses": [
                    {"courseCode": "CSCA08H3", "grade": "A", "mark": "90", "credits": "0.5", "title": None, "courseAverage": None},
                    {"courseCode": "MATA30H3", "grade": "B", "mark": "70", "credits": "0.5", "title": None, "courseAverage": None},
                ]
            }],
        }
        with patch("api.services.acorn_service.get_latest_import_for_user", return_value=data):
            result = get_academic_history("u1")
        marks = [float(c["mark"]) for c in result["courses_by_mark"]]
        assert marks == sorted(marks)


# ── claim_latest_import_for_user ───────────────────────────────────────────────

class TestClaimLatestImportForUser:
    def test_raises_for_blank_import_code(self):
        from api.services.acorn_service import claim_latest_import_for_user
        from api.integrations.acorn_store import AcornStoreError
        with pytest.raises(AcornStoreError):
            claim_latest_import_for_user("", "u1")

    def test_raises_for_blank_user_id(self):
        from api.services.acorn_service import claim_latest_import_for_user
        from api.integrations.acorn_store import AcornStoreError
        with pytest.raises(AcornStoreError):
            claim_latest_import_for_user("ABC123", "")

    def test_returns_none_when_row_not_found(self):
        from api.services.acorn_service import claim_latest_import_for_user
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[])
        with patch("api.services.acorn_service.get_supabase_client", return_value=mock_sb):
            result = claim_latest_import_for_user("ABC123", "u1")
        assert result is None

    def test_success_returns_data(self):
        from api.services.acorn_service import claim_latest_import_for_user
        mock_sb = _mock_sb()
        row = {
            "id": "row-1",
            "data": {"importCode": "ABC123", "courses": []},
            "imported_at": "2024-01-01T00:00:00+00:00",
        }
        mock_sb.table.return_value.execute.side_effect = [
            MagicMock(data=[row]),   # lookup
            MagicMock(data=[]),       # update
        ]
        with patch("api.services.acorn_service.get_supabase_client", return_value=mock_sb):
            result = claim_latest_import_for_user("ABC123", "u1")
        assert result is not None
        assert result["importedAt"] == "2024-01-01T00:00:00+00:00"

    def test_raises_on_lookup_error(self):
        from api.services.acorn_service import claim_latest_import_for_user, AcornServiceError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.services.acorn_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(AcornServiceError, match="Failed to load ACORN import to claim"):
                claim_latest_import_for_user("ABC123", "u1")

    def test_raises_on_update_error(self):
        from api.services.acorn_service import claim_latest_import_for_user, AcornServiceError
        mock_sb = _mock_sb()
        row = {
            "id": "row-1",
            "data": {"importCode": "ABC123", "courses": []},
            "imported_at": "2024-01-01T00:00:00+00:00",
        }
        mock_sb.table.return_value.execute.side_effect = [
            MagicMock(data=[row]),        # lookup succeeds
            Exception("update failed"),   # update raises
        ]
        with patch("api.services.acorn_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(AcornServiceError, match="Failed to claim"):
                claim_latest_import_for_user("ABC123", "u1")


# ── store_acorn_pdf_import ────────────────────────────────────────────────────

class TestStoreAcornPdfImport:
    def test_raises_for_blank_user_id(self):
        from api.services.acorn_service import store_acorn_pdf_import, AcornServiceError
        with pytest.raises(AcornServiceError, match="user_id must be provided"):
            store_acorn_pdf_import("", {"courses": []})

    def test_raises_for_none_user_id(self):
        from api.services.acorn_service import store_acorn_pdf_import, AcornServiceError
        with pytest.raises(AcornServiceError, match="user_id must be provided"):
            store_acorn_pdf_import(None, {"courses": []})

    def test_success_returns_parsed_data(self):
        from api.services.acorn_service import store_acorn_pdf_import
        mock_sb = _mock_sb()
        inserted_row = {"id": 1, "data": {"courses": []}}
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[inserted_row])
        parsed = {"courses": [{"courseCode": "CSCA08H3"}], "importedAt": "2024-06-01T00:00:00+00:00"}
        with patch("api.services.acorn_service.get_supabase_client", return_value=mock_sb):
            result = store_acorn_pdf_import("user-abc", parsed)
        assert result is parsed
        call_args = mock_sb.table.return_value.insert.call_args[0][0]
        assert call_args["user_id"] == "user-abc"
        assert call_args["import_code"].startswith("pdf-user-abc")
        assert call_args["data"] is parsed

    def test_uses_parsed_imported_at(self):
        from api.services.acorn_service import store_acorn_pdf_import
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[{"id": 1}])
        parsed = {"courses": [], "importedAt": "2025-01-15T12:00:00+00:00"}
        with patch("api.services.acorn_service.get_supabase_client", return_value=mock_sb):
            store_acorn_pdf_import("u1", parsed)
        call_args = mock_sb.table.return_value.insert.call_args[0][0]
        assert call_args["imported_at"] == "2025-01-15T12:00:00+00:00"

    def test_generates_imported_at_when_missing(self):
        from api.services.acorn_service import store_acorn_pdf_import
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[{"id": 1}])
        parsed = {"courses": []}
        with patch("api.services.acorn_service.get_supabase_client", return_value=mock_sb):
            store_acorn_pdf_import("u1", parsed)
        call_args = mock_sb.table.return_value.insert.call_args[0][0]
        assert call_args["imported_at"] is not None

    def test_raises_on_supabase_error(self):
        from api.services.acorn_service import store_acorn_pdf_import, AcornServiceError
        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB down")
        with patch("api.services.acorn_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(AcornServiceError, match="Failed to store PDF ACORN import"):
                store_acorn_pdf_import("u1", {"courses": []})

    def test_raises_when_no_rows_returned(self):
        from api.services.acorn_service import store_acorn_pdf_import, AcornServiceError
        mock_sb = _mock_sb()
        mock_sb.table.return_value.execute.return_value = MagicMock(data=[])
        with patch("api.services.acorn_service.get_supabase_client", return_value=mock_sb):
            with pytest.raises(AcornServiceError, match="Supabase returned no inserted"):
                store_acorn_pdf_import("u1", {"courses": []})


# ── upload_acorn_pdf (router endpoint) ────────────────────────────────────────

def _user(user_id="u-test"):
    return {"user_id": user_id, "email": "test@example.com"}


def _make_upload(filename="Academic History.pdf", content=b"%PDF-fake"):
    import asyncio
    upload = MagicMock()
    upload.filename = filename

    async def _read():
        return content

    upload.read = _read
    return upload


class TestUploadAcornPdf:
    async def test_rejects_non_pdf(self):
        from api.routers.acorn import upload_acorn_pdf
        upload = _make_upload(filename="history.docx")
        resp = await upload_acorn_pdf(file=upload, current_user=_user())
        assert resp.status_code == 400
        assert b"Only PDF" in resp.body

    async def test_rejects_oversized_file(self):
        from api.routers.acorn import upload_acorn_pdf
        upload = _make_upload(content=b"x" * (10 * 1024 * 1024 + 1))
        resp = await upload_acorn_pdf(file=upload, current_user=_user())
        assert resp.status_code == 400
        assert b"10 MB" in resp.body

    async def test_returns_400_on_parse_error(self):
        from api.routers.acorn import upload_acorn_pdf
        from api.integrations.acorn_pdf_parser import AcornPdfParseError
        upload = _make_upload()
        with patch("api.routers.acorn.parse_acorn_pdf", side_effect=AcornPdfParseError("bad pdf")):
            resp = await upload_acorn_pdf(file=upload, current_user=_user())
        assert resp.status_code == 400
        assert b"bad pdf" in resp.body

    async def test_returns_500_on_storage_error(self):
        from api.routers.acorn import upload_acorn_pdf
        from api.services.acorn_service import AcornServiceError
        upload = _make_upload()
        parsed = {"courses": [], "terms": []}
        with patch("api.routers.acorn.parse_acorn_pdf", return_value=parsed):
            with patch("api.routers.acorn.store_acorn_pdf_import", side_effect=AcornServiceError("db down")):
                resp = await upload_acorn_pdf(file=upload, current_user=_user())
        assert resp.status_code == 500
        assert b"db down" in resp.body

    async def test_success_returns_data(self):
        from api.routers.acorn import upload_acorn_pdf
        upload = _make_upload()
        parsed = {"courses": [{"courseCode": "CSCA08H3"}], "terms": [], "importedAt": "2024-01-01"}
        with patch("api.routers.acorn.parse_acorn_pdf", return_value=parsed):
            with patch("api.routers.acorn.store_acorn_pdf_import", return_value=parsed):
                resp = await upload_acorn_pdf(file=upload, current_user=_user())
        assert resp.status_code == 200
        import json
        body = json.loads(resp.body)
        assert body["ok"] is True
        assert body["data"]["courses"][0]["courseCode"] == "CSCA08H3"
