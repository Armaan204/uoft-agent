"""
tests/test_graduation_extended.py — additional tests for integrations/graduation_service.py.

Covers the Supabase cache layer, URL discovery, LLM extraction, and public API.
All external calls (Supabase, Anthropic API, HTTP) are mocked.
"""

import json
import pytest
from unittest.mock import MagicMock, patch


# ── pure helper functions ─────────────────────────────────────────────────────

class TestHtmlToText:
    def test_strips_html_tags(self):
        from integrations.graduation_service import _html_to_text
        result = _html_to_text("<p>Hello <b>world</b></p>")
        assert "Hello" in result
        assert "world" in result
        assert "<" not in result

    def test_removes_script_blocks(self):
        from integrations.graduation_service import _html_to_text
        result = _html_to_text("<script>alert('xss')</script><p>content</p>")
        assert "alert" not in result
        assert "content" in result

    def test_collapses_whitespace(self):
        from integrations.graduation_service import _html_to_text
        result = _html_to_text("<p>  a   b   c  </p>")
        assert "   " not in result


class TestHasCourseRequirements:
    def test_returns_false_for_few_codes(self):
        from integrations.graduation_service import _has_course_requirements
        assert _has_course_requirements("CSCA08H3 MATA30H3") is False

    def test_returns_true_for_enough_codes(self):
        from integrations.graduation_service import _has_course_requirements
        text = "CSCA08H3 CSCA48H3 MATA30H3 STAC32H3"
        assert _has_course_requirements(text) is True


class TestSlugifyUtsc:
    def test_basic_slug(self):
        from integrations.graduation_service import _slugify_utsc
        assert _slugify_utsc("Computer Science") == "computer-science"

    def test_expands_parens(self):
        from integrations.graduation_service import _slugify_utsc
        assert "co-operative" in _slugify_utsc("Science (Co-operative)")

    def test_drops_prepositions(self):
        from integrations.graduation_service import _slugify_utsc
        slug = _slugify_utsc("Specialist in Statistics")
        assert "-in-" not in slug
        assert "statistics" in slug

    def test_multiple_spaces_normalized(self):
        from integrations.graduation_service import _slugify_utsc
        slug = _slugify_utsc("  Computer   Science  ")
        assert "--" not in slug


class TestGenerateUtscSlugVariants:
    def test_returns_base_slug(self):
        from integrations.graduation_service import _generate_utsc_slug_variants
        variants = _generate_utsc_slug_variants("Computer Science Specialist")
        assert any("computer" in v and "science" in v for v in variants)

    def test_no_duplicate_variants(self):
        from integrations.graduation_service import _generate_utsc_slug_variants
        variants = _generate_utsc_slug_variants("Computer Science Specialist")
        assert len(variants) == len(set(variants))


class TestCollectRequiredCourses:
    def test_collects_required_and_list_courses(self):
        from integrations.graduation_service import collect_required_courses
        reqs = {
            "groups": [{
                "items": [
                    {"type": "required", "courses": ["CSCA08H3", "CSCA48H3"]},
                    {"type": "n_credits_from_list", "courses": ["STAC32H3"]},
                    {"type": "open_pool", "courses": []},
                ]
            }]
        }
        codes = collect_required_courses(reqs)
        assert "CSCA08H3" in codes
        assert "CSCA48H3" in codes
        assert "STAC32H3" in codes

    def test_returns_empty_for_no_groups(self):
        from integrations.graduation_service import collect_required_courses
        assert collect_required_courses({"groups": []}) == []


class TestIsValidProgramPage:
    def test_accepts_page_with_course_codes(self):
        from integrations.graduation_service import _is_valid_program_page
        page = {
            "url": "https://utsc.calendar.utoronto.ca/cs",
            "text": "CSCA08H3 CSCA48H3 MATA30H3 STAC32H3 complete the following",
        }
        assert _is_valid_program_page(page) is True

    def test_rejects_page_without_course_codes(self):
        from integrations.graduation_service import _is_valid_program_page
        page = {"url": "https://utsc.calendar.utoronto.ca/cs", "text": "Welcome to our programs."}
        assert _is_valid_program_page(page) is False

    def test_accepts_keyword_matching_coop_page_without_course_codes(self):
        from integrations.graduation_service import _is_valid_program_page
        page = {"url": "https://utsc.calendar.utoronto.ca/computer-science-co-operative", "text": "Co-op overview"}
        assert _is_valid_program_page(page, is_coop=True, keywords=["computer"]) is True


# ── cache helpers ─────────────────────────────────────────────────────────────

class TestLoadCache:
    def test_returns_requirements_on_hit(self):
        from integrations.graduation_service import _load_cache
        fake_reqs = {"groups": [], "program_name": "Computer Science Specialist"}
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value \
            .execute.return_value.data = [{"requirements": fake_reqs, "extraction_status": "ok"}]

        with patch("integrations.graduation_service._db", return_value=mock_db):
            result = _load_cache("Computer Science Specialist")

        assert result == fake_reqs

    def test_returns_none_on_miss(self):
        from integrations.graduation_service import _load_cache
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value \
            .execute.return_value.data = []

        with patch("integrations.graduation_service._db", return_value=mock_db):
            result = _load_cache("Unknown Program")

        assert result is None

    def test_returns_none_on_failed_status(self):
        from integrations.graduation_service import _load_cache
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value \
            .execute.return_value.data = [{"requirements": {}, "extraction_status": "failed"}]

        with patch("integrations.graduation_service._db", return_value=mock_db):
            result = _load_cache("Computer Science Specialist")

        assert result is None

    def test_returns_none_on_db_exception(self):
        from integrations.graduation_service import _load_cache
        mock_db = MagicMock()
        mock_db.table.side_effect = Exception("connection error")

        with patch("integrations.graduation_service._db", return_value=mock_db):
            result = _load_cache("Any Program")

        assert result is None


class TestSaveCache:
    def test_calls_upsert(self):
        from integrations.graduation_service import _save_cache
        mock_db = MagicMock()

        with patch("integrations.graduation_service._db", return_value=mock_db):
            _save_cache(
                acorn_name="Computer Science Specialist",
                canonical_name="Computer Science Specialist",
                program_code="SCSPE1234Y",
                campus="UTSC",
                calendar_url="https://utsc.calendar.utoronto.ca/cs",
                requirements={"groups": []},
                academic_year="2024-2025",
            )

        mock_db.table.return_value.upsert.assert_called_once()

    def test_silently_swallows_db_exception(self):
        """Cache save should never raise — swallows all exceptions."""
        from integrations.graduation_service import _save_cache
        mock_db = MagicMock()
        mock_db.table.side_effect = Exception("DB error")

        with patch("integrations.graduation_service._db", return_value=mock_db):
            # Should not raise
            _save_cache("name", "canonical", None, "UTSC", "url", {}, "2024-2025")


# ── _fetch_page ───────────────────────────────────────────────────────────────

class TestFetchPage:
    def test_returns_dict_on_200(self):
        from integrations.graduation_service import _fetch_page
        mock_resp = MagicMock(status_code=200, text="<html>CSCA08H3 content</html>")
        with patch("integrations.graduation_service.requests.get", return_value=mock_resp):
            result = _fetch_page("http://example.com")
        assert result is not None
        assert "url" in result
        assert "text" in result

    def test_returns_none_on_404(self):
        from integrations.graduation_service import _fetch_page
        mock_resp = MagicMock(status_code=404)
        with patch("integrations.graduation_service.requests.get", return_value=mock_resp):
            result = _fetch_page("http://example.com/missing")
        assert result is None

    def test_returns_none_on_exception(self):
        from integrations.graduation_service import _fetch_page
        with patch("integrations.graduation_service.requests.get", side_effect=Exception("timeout")):
            result = _fetch_page("http://example.com")
        assert result is None


# ── _extract_with_llm ─────────────────────────────────────────────────────────

class TestExtractWithLlm:
    def _llm_response(self, text: str):
        msg = MagicMock()
        msg.content = [MagicMock(text=text)]
        return msg

    def test_returns_parsed_requirements(self):
        from integrations.graduation_service import _extract_with_llm
        fake_result = {"groups": [{"id": "core", "items": []}], "program_name": "CS"}
        mock_llm = MagicMock()
        mock_llm.messages.create.return_value = self._llm_response(json.dumps(fake_result))

        with patch("integrations.graduation_service._llm", return_value=mock_llm):
            result = _extract_with_llm("page text here", "http://example.com")

        assert result["program_name"] == "CS"

    def test_raises_on_missing_groups_key(self):
        from integrations.graduation_service import _extract_with_llm
        mock_llm = MagicMock()
        mock_llm.messages.create.return_value = self._llm_response('{"program_name": "CS"}')

        with patch("integrations.graduation_service._llm", return_value=mock_llm):
            with pytest.raises(ValueError, match="missing 'groups'"):
                _extract_with_llm("page text", "http://example.com")

    def test_raises_on_invalid_json(self):
        from integrations.graduation_service import _extract_with_llm
        mock_llm = MagicMock()
        mock_llm.messages.create.return_value = self._llm_response("not json")

        with patch("integrations.graduation_service._llm", return_value=mock_llm):
            with pytest.raises(Exception):
                _extract_with_llm("page text", "http://example.com")


# ── get_program_requirements ──────────────────────────────────────────────────

class TestGetProgramRequirements:
    def test_cache_hit_returns_cached(self):
        from integrations.graduation_service import get_program_requirements
        cached = {"groups": [], "program_name": "Computer Science Specialist"}

        with patch("integrations.graduation_service._load_cache", return_value=cached):
            result = get_program_requirements("Computer Science Specialist")

        assert result == cached

    def test_cache_miss_discovers_url_and_extracts(self):
        from integrations.graduation_service import get_program_requirements
        fake_page = {
            "url": "https://utsc.calendar.utoronto.ca/cs",
            "text": "CSCA08H3 CSCA48H3 MATA30H3 STAC32H3 content",
            "html": "<html>content</html>",
        }
        fake_reqs = {
            "groups": [{"id": "core", "items": []}],
            "program_name": "Computer Science Specialist",
            "academic_year": "2024-2025",
        }

        with patch("integrations.graduation_service._load_cache", return_value=None), \
             patch("integrations.graduation_service._discover_calendar_url", return_value=fake_page), \
             patch("integrations.graduation_service._extract_with_llm", return_value=fake_reqs), \
             patch("integrations.graduation_service._save_cache"):
            result = get_program_requirements("Computer Science Specialist")

        assert result["program_name"] == "Computer Science Specialist"

    def test_url_discovery_failure_returns_none(self):
        from integrations.graduation_service import get_program_requirements

        with patch("integrations.graduation_service._load_cache", return_value=None), \
             patch("integrations.graduation_service._discover_calendar_url", return_value=None), \
             patch("integrations.graduation_service._save_failed"):
            result = get_program_requirements("Unknown Program XYZ")

        assert result is None

    def test_llm_extraction_failure_returns_none(self):
        from integrations.graduation_service import get_program_requirements
        fake_page = {
            "url": "https://utsc.calendar.utoronto.ca/cs",
            "text": "some content",
            "html": "<html></html>",
        }

        with patch("integrations.graduation_service._load_cache", return_value=None), \
             patch("integrations.graduation_service._discover_calendar_url", return_value=fake_page), \
             patch("integrations.graduation_service._extract_with_llm", side_effect=ValueError("bad schema")), \
             patch("integrations.graduation_service._save_failed"):
            result = get_program_requirements("Computer Science Specialist")

        assert result is None

    def test_force_refresh_clears_cache_first(self):
        from integrations.graduation_service import get_program_requirements
        fake_page = {
            "url": "https://utsc.calendar.utoronto.ca/cs",
            "text": "CSCA08H3 CSCA48H3 MATA30H3 STAC32H3",
            "html": "<html></html>",
        }
        fake_reqs = {"groups": [], "program_name": "CS", "academic_year": "2024-2025"}

        with patch("integrations.graduation_service.clear_cache") as mock_clear, \
             patch("integrations.graduation_service._discover_calendar_url", return_value=fake_page), \
             patch("integrations.graduation_service._extract_with_llm", return_value=fake_reqs), \
             patch("integrations.graduation_service._save_cache"):
            get_program_requirements("Computer Science Specialist", force_refresh=True)

        mock_clear.assert_called_once_with("Computer Science Specialist")

    def test_coop_program_strips_qualifier_for_url_discovery(self):
        from integrations.graduation_service import get_program_requirements
        fake_page = {
            "url": "https://utsc.calendar.utoronto.ca/cs",
            "text": "CSCA08H3 CSCA48H3 MATA30H3 STAC32H3",
            "html": "<html></html>",
        }
        fake_reqs = {"groups": [], "program_name": "CS", "academic_year": "2024-2025"}

        calls = []

        def fake_discover(name, campus, is_coop):
            calls.append(name)
            return fake_page

        with patch("integrations.graduation_service._load_cache", return_value=None), \
             patch("integrations.graduation_service._discover_calendar_url", side_effect=fake_discover), \
             patch("integrations.graduation_service._extract_with_llm", return_value=fake_reqs), \
             patch("integrations.graduation_service._save_cache"):
            get_program_requirements("Computer Science (Co-operative)")

        assert any("co-op" not in n.lower() or "co-operative" not in n.lower() for n in calls)

    def test_coop_program_sets_is_coop_flag(self):
        from integrations.graduation_service import get_program_requirements
        fake_page = {
            "url": "https://utsc.calendar.utoronto.ca/cs-coop",
            "text": "CSCA08H3 CSCA48H3 MATA30H3 STAC32H3",
            "html": "<html></html>",
        }
        fake_reqs = {"groups": [], "program_name": "CS Co-op", "academic_year": "2024-2025"}

        with patch("integrations.graduation_service._load_cache", return_value=None), \
             patch("integrations.graduation_service._discover_calendar_url", return_value=fake_page), \
             patch("integrations.graduation_service._extract_with_llm", return_value=fake_reqs), \
             patch("integrations.graduation_service._save_cache"):
            result = get_program_requirements("Computer Science (Co-operative)")

        assert result["is_coop"] is True


# ── _save_failed / clear_cache ────────────────────────────────────────────────

class TestSaveFailed:
    def test_calls_upsert_with_failed_status(self):
        from integrations.graduation_service import _save_failed
        mock_db = MagicMock()

        with patch("integrations.graduation_service._db", return_value=mock_db):
            _save_failed("Unknown Program", "no page found")

        mock_db.table.return_value.upsert.assert_called_once()
        call_args = mock_db.table.return_value.upsert.call_args[0][0]
        assert call_args["extraction_status"] == "failed"
        assert call_args["extraction_error"] == "no page found"

    def test_silently_swallows_exception(self):
        from integrations.graduation_service import _save_failed
        mock_db = MagicMock()
        mock_db.table.side_effect = Exception("DB down")

        with patch("integrations.graduation_service._db", return_value=mock_db):
            _save_failed("Any Program", "error msg")  # must not raise


class TestClearCache:
    def test_calls_delete_on_table(self):
        from integrations.graduation_service import clear_cache
        mock_db = MagicMock()

        with patch("integrations.graduation_service._db", return_value=mock_db):
            clear_cache("Computer Science Specialist")

        mock_db.table.return_value.delete.assert_called_once()

    def test_silently_swallows_exception(self):
        from integrations.graduation_service import clear_cache
        mock_db = MagicMock()
        mock_db.table.side_effect = Exception("DB down")

        with patch("integrations.graduation_service._db", return_value=mock_db):
            clear_cache("Any Program")  # must not raise


# ── _program_url_keywords ─────────────────────────────────────────────────────

class TestProgramUrlKeywords:
    def test_filters_stop_words(self):
        from integrations.graduation_service import _program_url_keywords
        keywords = _program_url_keywords("Specialist Program in Statistics")
        assert "statistics" in keywords
        assert "specialist" not in keywords
        assert "program" not in keywords
        assert "in" not in keywords

    def test_filters_short_words(self):
        from integrations.graduation_service import _program_url_keywords
        keywords = _program_url_keywords("CS and AI")
        assert "cs" not in keywords
        assert "ai" not in keywords

    def test_returns_meaningful_words(self):
        from integrations.graduation_service import _program_url_keywords
        keywords = _program_url_keywords("Computer Science Specialist")
        assert "computer" in keywords


# ── _ddg_search_urls ──────────────────────────────────────────────────────────

class TestDdgSearchUrls:
    def test_returns_matching_urls(self):
        from integrations.graduation_service import _ddg_search_urls
        import urllib.parse
        encoded_url = urllib.parse.quote("https://utsc.calendar.utoronto.ca/cs", safe="")
        mock_html = f'<a href="/l/?uddg={encoded_url}&rut=1">link</a>'
        mock_resp = MagicMock(status_code=200, text=mock_html)
        with patch("integrations.graduation_service.requests.get", return_value=mock_resp):
            result = _ddg_search_urls("CS specialist UTSC", "https://utsc.calendar.utoronto.ca")
        assert any("utsc.calendar.utoronto.ca" in url for url in result)

    def test_returns_empty_on_non_200(self):
        from integrations.graduation_service import _ddg_search_urls
        mock_resp = MagicMock(status_code=403)
        with patch("integrations.graduation_service.requests.get", return_value=mock_resp):
            result = _ddg_search_urls("query", "https://utsc.calendar.utoronto.ca")
        assert result == []

    def test_returns_empty_on_exception(self):
        from integrations.graduation_service import _ddg_search_urls
        with patch("integrations.graduation_service.requests.get", side_effect=Exception("timeout")):
            result = _ddg_search_urls("query", "https://utsc.calendar.utoronto.ca")
        assert result == []

    def test_filters_non_matching_domain(self):
        from integrations.graduation_service import _ddg_search_urls
        import urllib.parse
        encoded_url = urllib.parse.quote("https://other.example.com/page", safe="")
        mock_html = f'<a href="/l/?uddg={encoded_url}&rut=1">link</a>'
        mock_resp = MagicMock(status_code=200, text=mock_html)
        with patch("integrations.graduation_service.requests.get", return_value=mock_resp):
            result = _ddg_search_urls("query", "https://utsc.calendar.utoronto.ca")
        assert result == []


# ── _strip_coop_qualifier ─────────────────────────────────────────────────────

class TestStripCoopQualifier:
    def test_removes_co_operative(self):
        from integrations.graduation_service import _strip_coop_qualifier
        result = _strip_coop_qualifier("Computer Science (Co-operative)")
        assert "Co-operative" not in result
        assert "Computer Science" in result

    def test_removes_co_op(self):
        from integrations.graduation_service import _strip_coop_qualifier
        result = _strip_coop_qualifier("Statistics (Co-op)")
        assert "Co-op" not in result
        assert "Statistics" in result

    def test_no_change_for_regular_program(self):
        from integrations.graduation_service import _strip_coop_qualifier
        result = _strip_coop_qualifier("Computer Science Specialist")
        assert result == "Computer Science Specialist"

    def test_normalizes_whitespace(self):
        from integrations.graduation_service import _strip_coop_qualifier
        result = _strip_coop_qualifier("Statistics  (Co-op)  ")
        assert "  " not in result


# ── _discover_url_via_slug ────────────────────────────────────────────────────

class TestDiscoverUrlViaSlug:
    def test_returns_page_on_slug_match(self):
        from integrations.graduation_service import _discover_url_via_slug
        fake_page = {
            "url": "https://utsc.calendar.utoronto.ca/computer-science-specialist",
            "text": "CSCA08H3 CSCA48H3 MATA30H3 STAC32H3",
            "html": "<html></html>",
        }
        mock_llm = MagicMock()
        mock_llm.messages.create.return_value.content = [MagicMock(text='["computer-science-specialist"]')]

        with patch("integrations.graduation_service._llm", return_value=mock_llm), \
             patch("integrations.graduation_service._fetch_page", return_value=fake_page), \
             patch("integrations.graduation_service._is_valid_program_page", return_value=True):
            result = _discover_url_via_slug(
                "Computer Science Specialist",
                "https://utsc.calendar.utoronto.ca",
                False,
                ["computer", "science"],
            )
        assert result is not None
        assert "computer-science" in result["url"]

    def test_returns_none_when_no_slug_matches(self):
        from integrations.graduation_service import _discover_url_via_slug
        mock_llm = MagicMock()
        mock_llm.messages.create.return_value.content = [MagicMock(text='[]')]

        with patch("integrations.graduation_service._llm", return_value=mock_llm), \
             patch("integrations.graduation_service._fetch_page", return_value=None):
            result = _discover_url_via_slug(
                "Unknown Specialist XYZ",
                "https://utsc.calendar.utoronto.ca",
                False,
                ["unknown"],
            )
        assert result is None


class TestDiscoverCalendarUrlFallback:
    def test_slug_404_then_web_search_success(self):
        from integrations.graduation_service import _discover_calendar_url
        page = {
            "url": "https://utsc.calendar.utoronto.ca/computer-science-specialist",
            "text": "CSCA08H3 CSCA48H3 MATA30H3",
            "html": "<html></html>",
        }
        with patch("integrations.graduation_service._discover_url_via_slug", return_value=None), \
             patch("integrations.graduation_service._discover_url_via_web_search", return_value=page):
            result = _discover_calendar_url("Computer Science Specialist", "UTSC", False)
        assert result == page


class TestAdditionalDiscoveryHelpers:
    def test_slugify_strips_symbols(self):
        from integrations.graduation_service import _slugify
        assert _slugify("Computer Science & Stats") == "computer-science-stats"

    def test_find_base_specialist_url_returns_none_when_not_coop_slug(self):
        from integrations.graduation_service import _find_base_specialist_url
        assert _find_base_specialist_url("https://utsc.calendar.utoronto.ca/computer-science", "https://utsc.calendar.utoronto.ca") is None

    def test_discover_url_via_web_search_uses_ddg_fallback(self):
        from integrations.graduation_service import _discover_url_via_web_search
        page = {"url": "https://utsc.calendar.utoronto.ca/cs", "text": "CSCA08H3", "html": ""}
        with patch("integrations.graduation_service._anthropic_web_search_url", return_value=None), \
             patch("integrations.graduation_service._ddg_search_urls", return_value=["https://utsc.calendar.utoronto.ca/cs"]), \
             patch("integrations.graduation_service._fetch_page", return_value=page):
            result = _discover_url_via_web_search("Computer Science Specialist", "https://utsc.calendar.utoronto.ca", False)
        assert result == page

    def test_anthropic_web_search_returns_none_on_exception(self):
        from integrations.graduation_service import _anthropic_web_search_url
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("boom")
        with patch("anthropic.Anthropic", return_value=mock_client):
            assert _anthropic_web_search_url("Computer Science Specialist", "https://utsc.calendar.utoronto.ca") is None


class TestGraduationAdditionalHelpers:
    def test_db_and_llm_helpers_build_clients(self, monkeypatch):
        from integrations.graduation_service import _db, _llm
        monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "supabase-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
        with patch("integrations.graduation_service.create_client", return_value="db-client") as mock_create, \
             patch("integrations.graduation_service.anthropic.Anthropic", return_value="llm-client") as mock_llm:
            assert _db() == "db-client"
            assert _llm() == "llm-client"
        mock_create.assert_called_once_with("https://example.supabase.co", "supabase-key")
        mock_llm.assert_called_once_with(api_key="anthropic-key")

    def test_current_academic_year_branches(self):
        from integrations.graduation_service import _current_academic_year
        from datetime import datetime, timezone
        with patch("integrations.graduation_service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 10, 1, tzinfo=timezone.utc)
            assert _current_academic_year() == "2026-2027"
        with patch("integrations.graduation_service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 1, tzinfo=timezone.utc)
            assert _current_academic_year() == "2025-2026"

    def test_discover_calendar_url_uses_default_base_and_slug_success(self):
        from integrations.graduation_service import _discover_calendar_url
        page = {"url": "https://utsc.calendar.utoronto.ca/x", "text": "CSCA08H3", "html": ""}
        with patch("integrations.graduation_service._discover_url_via_slug", return_value=page) as mock_slug:
            result = _discover_calendar_url("Program", "UNKNOWN", False)
        assert result == page
        assert "utsc.calendar.utoronto.ca" in mock_slug.call_args.args[1]

    def test_extract_with_llm_appends_coop_text(self):
        from integrations.graduation_service import _extract_with_llm
        mock_llm = MagicMock()
        mock_llm.messages.create.return_value.content = [MagicMock(text='{"groups": []}')]
        with patch("integrations.graduation_service._llm", return_value=mock_llm):
            _extract_with_llm("page text", "http://example.com", coop_text="coop text")
        prompt = mock_llm.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "CO-OP SPECIFIC REQUIREMENTS" in prompt

    def test_get_program_requirements_uses_current_year_default(self):
        from integrations.graduation_service import get_program_requirements
        fake_page = {"url": "https://utsc.calendar.utoronto.ca/cs", "text": "text", "html": "<html></html>"}
        fake_reqs = {"groups": [], "program_name": "CS"}
        with patch("integrations.graduation_service._load_cache", return_value=None), \
             patch("integrations.graduation_service._discover_calendar_url", return_value=fake_page), \
             patch("integrations.graduation_service._extract_with_llm", return_value=fake_reqs), \
             patch("integrations.graduation_service._current_academic_year", return_value="2026-2027"), \
             patch("integrations.graduation_service._save_cache") as mock_save:
            get_program_requirements("Computer Science Specialist")
        assert mock_save.call_args.kwargs["academic_year"] == "2026-2027"

    def test_generate_utsc_slug_variants_handles_codes_suffixes_and_renames(self):
        from integrations.graduation_service import _generate_utsc_slug_variants
        variants = _generate_utsc_slug_variants("Data Mining Specialist (SCIENCE) SCSPE1234Y")
        assert any("data-science" in variant or "data-mining" in variant for variant in variants)
        assert any(not variant.endswith("-science") for variant in variants)

    def test_is_valid_program_page_allows_coop_without_keywords_when_none_provided(self):
        from integrations.graduation_service import _is_valid_program_page
        page = {"url": "https://utsc.calendar.utoronto.ca/computer-science-co-operative", "text": "Co-op overview"}
        assert _is_valid_program_page(page, is_coop=True, keywords=None) is True

    def test_find_base_specialist_url_probes_candidates_until_match(self):
        from integrations.graduation_service import _find_base_specialist_url
        with patch("integrations.graduation_service._fetch_page", side_effect=[
            None,
            {"url": "x", "text": "not enough"},
            {"url": "x", "text": "CSCA08H3 CSCA48H3 MATA30H3 STAC32H3"},
        ]):
            result = _find_base_specialist_url(
                "https://utsc.calendar.utoronto.ca/co-operative-computer-science-specialist-scspx1234y",
                "https://utsc.calendar.utoronto.ca",
            )
        assert result.endswith("/computer-science-specialist-scspx1234y-science") or result.endswith("/computer-science-specialist-scspx1234y-arts") or result.endswith("/computer-science-specialist-scspx1234y-music") or result.endswith("/computer-science-specialist")

    def test_find_base_specialist_url_returns_none_after_exhausting_candidates(self):
        from integrations.graduation_service import _find_base_specialist_url
        with patch("integrations.graduation_service._fetch_page", return_value=None):
            result = _find_base_specialist_url(
                "https://utsc.calendar.utoronto.ca/co-operative-computer-science-specialist",
                "https://utsc.calendar.utoronto.ca",
            )
        assert result is None

    def test_find_base_specialist_url_skips_empty_candidate_slug(self):
        from integrations.graduation_service import _find_base_specialist_url
        with patch("integrations.graduation_service._fetch_page", return_value=None):
            assert _find_base_specialist_url(
                "https://utsc.calendar.utoronto.ca/co-operative-",
                "https://utsc.calendar.utoronto.ca",
            ) is None

    def test_anthropic_web_search_url_harvests_text_and_tool_loop(self):
        from integrations.graduation_service import _anthropic_web_search_url
        response = MagicMock()
        response.content = [MagicMock(text="See https://utsc.calendar.utoronto.ca/computer-science-specialist.")]
        response.stop_reason = "end_turn"
        mock_client = MagicMock()
        mock_client.messages.create.return_value = response
        with patch("anthropic.Anthropic", return_value=mock_client):
            result = _anthropic_web_search_url("Computer Science Specialist", "https://utsc.calendar.utoronto.ca")
        assert result == "https://utsc.calendar.utoronto.ca/computer-science-specialist"

        tool_response = MagicMock()
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "tool-1"
        tool_block.text = ""
        tool_response.content = [tool_block]
        tool_response.stop_reason = "tool_use"
        final_response = MagicMock()
        final_response.content = []
        final_response.stop_reason = "end_turn"
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [tool_response, final_response]
        with patch("anthropic.Anthropic", return_value=mock_client):
            assert _anthropic_web_search_url("Computer Science Specialist", "https://utsc.calendar.utoronto.ca") is None

        empty_tool_response = MagicMock()
        non_tool_block = MagicMock()
        non_tool_block.type = "text"
        non_tool_block.id = "x"
        non_tool_block.text = ""
        empty_tool_response.content = [non_tool_block]
        empty_tool_response.stop_reason = "tool_use"
        mock_client = MagicMock()
        mock_client.messages.create.return_value = empty_tool_response
        with patch("anthropic.Anthropic", return_value=mock_client):
            assert _anthropic_web_search_url("Computer Science Specialist", "https://utsc.calendar.utoronto.ca") is None

    def test_discover_url_via_web_search_falls_back_after_404(self):
        from integrations.graduation_service import _discover_url_via_web_search
        page = {"url": "https://utsc.calendar.utoronto.ca/cs", "text": "CSCA08H3", "html": ""}
        with patch("integrations.graduation_service._anthropic_web_search_url", return_value="https://utsc.calendar.utoronto.ca/missing"), \
             patch("integrations.graduation_service._fetch_page", side_effect=[None, page]), \
             patch("integrations.graduation_service._ddg_search_urls", return_value=["https://utsc.calendar.utoronto.ca/cs"]):
            result = _discover_url_via_web_search("Computer Science Specialist", "https://utsc.calendar.utoronto.ca", False)
        assert result == page

    def test_discover_url_via_web_search_returns_page_from_anthropic_url(self):
        from integrations.graduation_service import _discover_url_via_web_search
        page = {"url": "https://utsc.calendar.utoronto.ca/cs", "text": "CSCA08H3", "html": ""}
        with patch("integrations.graduation_service._anthropic_web_search_url", return_value="https://utsc.calendar.utoronto.ca/cs"), \
             patch("integrations.graduation_service._fetch_page", return_value=page):
            assert _discover_url_via_web_search("Computer Science Specialist", "https://utsc.calendar.utoronto.ca", False) == page

    def test_discover_url_via_web_search_returns_none_when_all_fallbacks_fail(self):
        from integrations.graduation_service import _discover_url_via_web_search
        with patch("integrations.graduation_service._anthropic_web_search_url", return_value=None), \
             patch("integrations.graduation_service._ddg_search_urls", return_value=[]):
            assert _discover_url_via_web_search("Computer Science Specialist", "https://utsc.calendar.utoronto.ca", False) is None

    def test_discover_url_via_slug_ignores_non_list_llm_output(self):
        from integrations.graduation_service import _discover_url_via_slug
        mock_llm = MagicMock()
        mock_llm.messages.create.return_value.content = [MagicMock(text='{"slug": "x"}')]
        with patch("integrations.graduation_service._llm", return_value=mock_llm), \
             patch("integrations.graduation_service._fetch_page", return_value=None):
            assert _discover_url_via_slug("Program", "https://utsc.calendar.utoronto.ca", False, ["program"]) is None

    def test_discover_url_via_slug_swallows_llm_exceptions(self):
        from integrations.graduation_service import _discover_url_via_slug
        with patch("integrations.graduation_service._llm", side_effect=RuntimeError("boom")), \
             patch("integrations.graduation_service._fetch_page", return_value=None):
            assert _discover_url_via_slug("Program", "https://utsc.calendar.utoronto.ca", False, ["program"]) is None

    def test_campus_digit_and_course_credits_helpers(self):
        from integrations.graduation_service import _campus_digit, _course_credits
        assert _campus_digit("CSC108H1") == "1"
        assert _campus_digit("CSCA08H3") == "3"
        assert _campus_digit("CSC108") is None
        assert _course_credits({"credits": 1.0}) == 1.0
        assert _course_credits({"credits": 0}) == 0.5
        assert _course_credits({"credits": "bad"}) == 0.5

    def test_match_group_unknown_item_type_and_match_coop_statuses(self):
        from integrations.graduation_service import _match_group, _match_coop
        group = {"id": "g1", "label": "Group", "credits_required": 0.5, "items": [{"id": "x", "type": "mystery"}]}
        result = _match_group(group, {}, set(), set())
        assert result["items"][0]["status"] == "unknown"

        coop = {"work_terms_required": 2, "preparation": [], "search_courses": [], "work_term_courses": []}
        remaining = _match_coop(coop, {}, set(), set())
        assert remaining["work_terms_status"] == "remaining"
        completed = _match_coop(
            {"work_terms_required": 1, "preparation": [], "search_courses": [], "work_term_courses": [{"id": "wt1", "type": "required", "courses": ["COPB50H3"], "credits": 0.5}]},
            {"COPB50H3": {"credits": 0.5, "grade": "A"}},
            set(),
            set(),
        )
        assert completed["work_terms_status"] == "satisfied"
