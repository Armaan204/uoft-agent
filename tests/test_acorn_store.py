"""
tests/test_acorn_store.py — tests for integrations/acorn_store.py

Uses tmp_path for file I/O so no real disk state is touched beyond the test.
"""

import json
import pytest
from unittest.mock import patch


# ── validate_payload — basic shape errors ────────────────────────────────────

class TestValidatePayloadBasicErrors:
    def test_raises_when_not_dict(self):
        from integrations.acorn_store import validate_payload, AcornStoreError
        with pytest.raises(AcornStoreError, match="JSON object"):
            validate_payload([1, 2, 3])

    def test_raises_when_import_code_missing(self):
        from integrations.acorn_store import validate_payload, AcornStoreError
        with pytest.raises(AcornStoreError, match="importCode"):
            validate_payload({"courses": []})

    def test_raises_when_import_code_whitespace_only(self):
        from integrations.acorn_store import validate_payload, AcornStoreError
        with pytest.raises(AcornStoreError, match="importCode"):
            validate_payload({"importCode": "   ", "courses": []})

    def test_raises_when_import_code_is_not_string(self):
        from integrations.acorn_store import validate_payload, AcornStoreError
        with pytest.raises(AcornStoreError, match="importCode"):
            validate_payload({"importCode": 123, "courses": []})


# ── validate_payload — terms format ──────────────────────────────────────────

class TestValidatePayloadTerms:
    def _base(self, extra=None):
        d = {
            "importCode": "ABC123",
            "terms": [
                {
                    "term": "Fall 2024",
                    "sessionalGpa": 3.5,
                    "cumulativeGpa": 3.4,
                    "courses": [
                        {"courseCode": "CSCA08H3", "grade": "A"}
                    ],
                }
            ],
        }
        if extra:
            d.update(extra)
        return d

    def test_valid_terms_returns_dict(self):
        from integrations.acorn_store import validate_payload
        result = validate_payload(self._base())
        assert result["importCode"] == "ABC123"
        assert "terms" in result
        assert len(result["terms"]) == 1
        assert result["courses"][0]["courseCode"] == "CSCA08H3"

    def test_base_helper_extra_kwarg_applied(self):
        from integrations.acorn_store import validate_payload
        result = validate_payload(self._base(extra={"sourceUrl": "http://example.com"}))
        assert result["sourceUrl"] == "http://example.com"

    def test_raises_when_term_is_not_dict(self):
        from integrations.acorn_store import validate_payload, AcornStoreError
        payload = {"importCode": "ABC", "terms": ["not-a-dict"]}
        with pytest.raises(AcornStoreError, match="Term at index"):
            validate_payload(payload)

    def test_raises_when_course_in_term_is_not_dict(self):
        from integrations.acorn_store import validate_payload, AcornStoreError
        payload = {
            "importCode": "ABC",
            "terms": [{"term": "Fall", "courses": ["not-a-dict"]}],
        }
        with pytest.raises(AcornStoreError, match="Course at term"):
            validate_payload(payload)

    def test_raises_when_course_in_term_missing_course_code(self):
        from integrations.acorn_store import validate_payload, AcornStoreError
        payload = {
            "importCode": "ABC",
            "terms": [{"term": "Fall", "courses": [{"title": "No code"}]}],
        }
        with pytest.raises(AcornStoreError, match="courseCode"):
            validate_payload(payload)

    def test_non_numeric_gpa_normalised_to_none(self):
        from integrations.acorn_store import validate_payload
        payload = {
            "importCode": "ABC",
            "terms": [{"term": "Fall", "sessionalGpa": "3.5", "cumulativeGpa": None, "courses": [
                {"courseCode": "CSCA08H3"}
            ]}],
        }
        result = validate_payload(payload)
        assert result["terms"][0]["sessionalGpa"] is None
        assert result["terms"][0]["cumulativeGpa"] is None

    def test_courses_derived_from_terms(self):
        from integrations.acorn_store import validate_payload
        payload = {
            "importCode": "TEST",
            "terms": [
                {"term": "Fall", "courses": [{"courseCode": "CSCA08H3"}]},
                {"term": "Winter", "courses": [{"courseCode": "CSCA67H3"}]},
            ],
        }
        result = validate_payload(payload)
        assert len(result["courses"]) == 2


# ── validate_payload — flat courses format ────────────────────────────────────

class TestValidatePayloadFlatCourses:
    def test_valid_flat_courses(self):
        from integrations.acorn_store import validate_payload
        payload = {
            "importCode": "XYZ",
            "courses": [{"courseCode": "CSC490H1", "grade": "B+"}],
        }
        result = validate_payload(payload)
        assert result["courses"][0]["courseCode"] == "CSC490H1"
        assert "terms" not in result

    def test_raises_when_no_courses_or_terms(self):
        from integrations.acorn_store import validate_payload, AcornStoreError
        with pytest.raises(AcornStoreError, match="courses"):
            validate_payload({"importCode": "XYZ"})

    def test_raises_when_courses_not_list(self):
        from integrations.acorn_store import validate_payload, AcornStoreError
        with pytest.raises(AcornStoreError, match="courses"):
            validate_payload({"importCode": "XYZ", "courses": "not-a-list"})

    def test_raises_when_flat_course_not_dict(self):
        from integrations.acorn_store import validate_payload, AcornStoreError
        with pytest.raises(AcornStoreError, match="Course at index"):
            validate_payload({"importCode": "XYZ", "courses": ["not-a-dict"]})

    def test_raises_when_flat_course_missing_code(self):
        from integrations.acorn_store import validate_payload, AcornStoreError
        with pytest.raises(AcornStoreError, match="courseCode"):
            validate_payload({"importCode": "XYZ", "courses": [{"title": "No code"}]})


# ── validate_payload — programs ────────────────────────────────────────────────

class TestValidatePayloadPrograms:
    def test_programs_normalised(self):
        from integrations.acorn_store import validate_payload
        payload = {
            "importCode": "ABC",
            "courses": [{"courseCode": "CSC490H1"}],
            "programs": [{"programName": "Computer Science", "enrollmentStatus": "Active"}],
        }
        result = validate_payload(payload)
        assert "programs" in result
        assert result["programs"][0]["programName"] == "Computer Science"

    def test_raises_when_program_not_dict(self):
        from integrations.acorn_store import validate_payload, AcornStoreError
        payload = {
            "importCode": "ABC",
            "courses": [{"courseCode": "CSC490H1"}],
            "programs": ["not-a-dict"],
        }
        with pytest.raises(AcornStoreError, match="Program at index"):
            validate_payload(payload)


# ── validate_payload — importedAt ────────────────────────────────────────────

class TestValidatePayloadImportedAt:
    def test_uses_provided_imported_at(self):
        from integrations.acorn_store import validate_payload
        payload = {
            "importCode": "ABC",
            "courses": [{"courseCode": "CSC490H1"}],
            "importedAt": "2024-09-01T00:00:00Z",
        }
        result = validate_payload(payload)
        assert result["importedAt"] == "2024-09-01T00:00:00Z"

    def test_uses_captured_at_fallback(self):
        from integrations.acorn_store import validate_payload
        payload = {
            "importCode": "ABC",
            "courses": [{"courseCode": "CSC490H1"}],
            "capturedAt": "2024-09-02T00:00:00Z",
        }
        result = validate_payload(payload)
        assert result["importedAt"] == "2024-09-02T00:00:00Z"

    def test_generates_timestamp_when_missing(self):
        from integrations.acorn_store import validate_payload
        payload = {"importCode": "ABC", "courses": [{"courseCode": "CSC490H1"}]}
        result = validate_payload(payload)
        assert result["importedAt"]  # not empty


# ── _normalise_import_code ───────────────────────────────────────────────────

class TestNormaliseImportCode:
    def test_uppercases_and_strips(self):
        from integrations.acorn_store import _normalise_import_code
        assert _normalise_import_code("  abc123  ") == "ABC123"

    def test_removes_special_chars(self):
        from integrations.acorn_store import _normalise_import_code
        assert _normalise_import_code("ab-cd_12") == "ABCD12"

    def test_raises_when_all_special_chars(self):
        from integrations.acorn_store import _normalise_import_code, AcornStoreError
        with pytest.raises(AcornStoreError, match="letters or numbers"):
            _normalise_import_code("---!!!")


# ── write_latest / read_latest / get_status ───────────────────────────────────

class TestWriteReadStatus:
    def test_write_then_read_roundtrip(self, tmp_path):
        from integrations.acorn_store import write_latest, read_latest, IMPORTS_DIR
        payload = {
            "importCode": "TESTCODE",
            "courses": [{"courseCode": "CSC490H1"}],
        }
        with patch("integrations.acorn_store.IMPORTS_DIR", tmp_path):
            written = write_latest(payload)
            recovered = read_latest("TESTCODE")
        assert written["importCode"] == "TESTCODE"
        assert recovered is not None
        assert recovered["importCode"] == "TESTCODE"

    def test_read_returns_none_when_no_file(self, tmp_path):
        from integrations.acorn_store import read_latest
        with patch("integrations.acorn_store.IMPORTS_DIR", tmp_path):
            result = read_latest("NOSUCHCODE")
        assert result is None

    def test_get_status_when_data_exists(self, tmp_path):
        from integrations.acorn_store import write_latest, get_status
        payload = {
            "importCode": "MYCODE",
            "courses": [{"courseCode": "CSC490H1"}, {"courseCode": "CSC343H1"}],
        }
        with patch("integrations.acorn_store.IMPORTS_DIR", tmp_path):
            write_latest(payload)
            status = get_status("MYCODE")
        assert status["exists"] is True
        assert status["courseCount"] == 2

    def test_get_status_when_no_data(self, tmp_path):
        from integrations.acorn_store import get_status
        with patch("integrations.acorn_store.IMPORTS_DIR", tmp_path):
            status = get_status("MISSING")
        assert status["exists"] is False
        assert status["importedAt"] is None
        assert status["importCode"] == "MISSING"

    def test_path_for_code_uses_normalised_name(self, tmp_path):
        from integrations.acorn_store import _path_for_code
        with patch("integrations.acorn_store.IMPORTS_DIR", tmp_path):
            path = _path_for_code("  my-code  ")
        assert path.name == "MYCODE.json"
