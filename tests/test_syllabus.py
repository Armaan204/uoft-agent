"""
tests/test_syllabus.py — unit tests for integrations/syllabus.py.

All HTTP calls (requests.get), Anthropic API calls, and PDF parsing are mocked.
"""

import io
import json
import pytest
from unittest.mock import MagicMock, patch, call


# ── pure helper functions ─────────────────────────────────────────────────────

class TestConfidenceHelpers:
    def test_confidence_exact_keyword(self):
        from api.integrations.syllabus import _confidence
        assert _confidence("syllabus.pdf") > 0

    def test_confidence_no_keyword(self):
        from api.integrations.syllabus import _confidence
        assert _confidence("lecture_notes.pdf") == 0.0

    def test_confidence_multiple_keywords(self):
        from api.integrations.syllabus import _confidence
        score_multi = _confidence("course syllabus outline.pdf")
        score_single = _confidence("syllabus.pdf")
        assert score_multi > score_single

    def test_score_candidate_picks_best(self):
        from api.integrations.syllabus import _score_candidate
        assert _score_candidate("random.pdf", "syllabus.pdf") > _score_candidate("random.pdf", "notes.pdf")

    def test_score_candidate_empty_inputs(self):
        from api.integrations.syllabus import _score_candidate
        assert _score_candidate() == 0.0

    def test_allowed_ext_pdf(self):
        from api.integrations.syllabus import _allowed_ext
        assert _allowed_ext("course_outline.pdf") is True

    def test_allowed_ext_docx(self):
        from api.integrations.syllabus import _allowed_ext
        assert _allowed_ext("syllabus.docx") is True

    def test_allowed_ext_txt_rejected(self):
        from api.integrations.syllabus import _allowed_ext
        assert _allowed_ext("notes.txt") is False

    def test_allowed_ext_no_ext(self):
        from api.integrations.syllabus import _allowed_ext
        assert _allowed_ext("noextension") is False

    def test_extract_page_slug_present(self):
        from api.integrations.syllabus import _extract_page_slug
        slug = _extract_page_slug("https://example.com/courses/123/pages/course-syllabus")
        assert slug == "course-syllabus"

    def test_extract_page_slug_missing(self):
        from api.integrations.syllabus import _extract_page_slug
        assert _extract_page_slug("https://example.com/courses/123/files/456") is None


class TestPickBestCandidate:
    def test_empty_returns_none(self):
        from api.integrations.syllabus import _pick_best_candidate
        assert _pick_best_candidate([]) is None

    def test_single_low_confidence_returns_none(self):
        from api.integrations.syllabus import _pick_best_candidate
        assert _pick_best_candidate([{"name": "file.pdf", "confidence": 0.0}]) is None

    def test_single_high_confidence_returned(self):
        from api.integrations.syllabus import _pick_best_candidate
        c = {"name": "syllabus.pdf", "confidence": 0.4, "url": "http://x"}
        assert _pick_best_candidate([c]) == c

    def test_clear_winner_returned(self):
        from api.integrations.syllabus import _pick_best_candidate
        best = {"name": "syllabus.pdf", "confidence": 0.6, "url": "http://x"}
        other = {"name": "notes.pdf", "confidence": 0.2, "url": "http://y"}
        assert _pick_best_candidate([best, other]) == best

    def test_tied_confidence_returns_none(self):
        from api.integrations.syllabus import _pick_best_candidate
        a = {"name": "syllabus.pdf", "confidence": 0.4, "url": "http://a"}
        b = {"name": "outline.pdf", "confidence": 0.4, "url": "http://b"}
        # Two with equal top confidence → no clear winner
        result = _pick_best_candidate([a, b])
        assert result is None


# ── file candidate collection ─────────────────────────────────────────────────

class TestCollectFileCandidates:
    def test_filters_allowed_extensions(self):
        from api.integrations.syllabus import _collect_file_candidates
        mock_client = MagicMock()
        mock_client.get_course_files.return_value = [
            {"display_name": "syllabus.pdf", "url": "http://a/syllabus.pdf"},
            {"display_name": "lecture.txt", "url": "http://a/lecture.txt"},
            {"display_name": "notes.docx",  "url": "http://a/notes.docx"},
        ]
        result = _collect_file_candidates(101, mock_client)
        names = [c["name"] for c in result]
        assert "syllabus.pdf" in names
        assert "notes.docx" in names
        assert "lecture.txt" not in names

    def test_returns_empty_on_exception(self):
        from api.integrations.syllabus import _collect_file_candidates
        mock_client = MagicMock()
        mock_client.get_course_files.side_effect = Exception("403 Forbidden")
        result = _collect_file_candidates(101, mock_client)
        assert result == []

    def test_confidence_set_on_candidates(self):
        from api.integrations.syllabus import _collect_file_candidates
        mock_client = MagicMock()
        mock_client.get_course_files.return_value = [
            {"display_name": "syllabus.pdf", "url": "http://a"}
        ]
        result = _collect_file_candidates(101, mock_client)
        assert "confidence" in result[0]

    def test_debug_wrapper_returns_error_when_inner_raises(self):
        from api.integrations.syllabus import _collect_file_candidates_debug
        with patch("api.integrations.syllabus._collect_file_candidates", side_effect=RuntimeError("boom")):
            candidates, error = _collect_file_candidates_debug(101, MagicMock())
        assert candidates == []
        assert error == "boom"


class TestCollectModuleCandidates:
    def test_collects_file_items_from_modules(self):
        from api.integrations.syllabus import _collect_module_candidates
        mock_client = MagicMock()
        mock_client.get_course_modules.return_value = [
            {"items": [
                {"type": "File", "content_id": 99, "title": "Course Syllabus"},
            ]},
        ]
        mock_client.get_file_metadata.return_value = {
            "display_name": "syllabus.pdf",
            "url": "http://a/syllabus.pdf",
        }
        result = _collect_module_candidates(101, mock_client)
        assert len(result) == 1
        assert result[0]["url"] == "http://a/syllabus.pdf"

    def test_skips_non_file_items(self):
        from api.integrations.syllabus import _collect_module_candidates
        mock_client = MagicMock()
        mock_client.get_course_modules.return_value = [
            {"items": [{"type": "Assignment", "content_id": 1, "title": "HW 1"}]},
        ]
        result = _collect_module_candidates(101, mock_client)
        assert result == []

    def test_returns_empty_on_modules_exception(self):
        from api.integrations.syllabus import _collect_module_candidates
        mock_client = MagicMock()
        mock_client.get_course_modules.side_effect = Exception("503")
        result = _collect_module_candidates(101, mock_client)
        assert result == []

    def test_deduplicates_by_file_id(self):
        from api.integrations.syllabus import _collect_module_candidates
        mock_client = MagicMock()
        mock_client.get_course_modules.return_value = [
            {"items": [
                {"type": "File", "content_id": 99, "title": "Syllabus"},
                {"type": "File", "content_id": 99, "title": "Syllabus duplicate"},
            ]},
        ]
        mock_client.get_file_metadata.return_value = {
            "display_name": "syllabus.pdf",
            "url": "http://a/syllabus.pdf",
        }
        result = _collect_module_candidates(101, mock_client)
        assert len(result) == 1

    def test_debug_wrapper_returns_error_when_inner_raises(self):
        from api.integrations.syllabus import _collect_module_candidates_debug
        with patch("api.integrations.syllabus._collect_module_candidates", side_effect=RuntimeError("boom")):
            candidates, error = _collect_module_candidates_debug(101, MagicMock())
        assert candidates == []
        assert error == "boom"

    def test_skips_metadata_exceptions_and_missing_urls(self):
        from api.integrations.syllabus import _collect_module_candidates
        mock_client = MagicMock()
        mock_client.get_course_modules.return_value = [
            {"items": [
                {"type": "File", "content_id": 1, "title": "Broken"},
                {"type": "File", "content_id": 2, "title": "Missing URL"},
                {"type": "File", "content_id": 3, "title": "Valid"},
            ]},
        ]

        def _meta(file_id):
            if file_id == 1:
                raise RuntimeError("bad metadata")
            if file_id == 2:
                return {"display_name": "outline.pdf"}
            return {"display_name": "syllabus.pdf", "url": "http://a/syllabus.pdf"}

        mock_client.get_file_metadata.side_effect = _meta
        result = _collect_module_candidates(101, mock_client)
        assert [c["url"] for c in result] == ["http://a/syllabus.pdf"]


class TestPageCandidateCollectors:
    def test_collect_syllabus_body_page_candidates(self):
        from api.integrations.syllabus import _collect_syllabus_body_page_candidates
        mock_client = MagicMock()
        mock_client.get_syllabus.return_value = {
            "syllabus_body": '<a href="/courses/101/pages/course-outline">Course Outline</a>'
        }
        result = _collect_syllabus_body_page_candidates(101, mock_client)
        assert result[0]["page_slug"] == "course-outline"

    def test_collect_module_page_candidates(self):
        from api.integrations.syllabus import _collect_module_page_candidates
        mock_client = MagicMock()
        mock_client.get_course_modules.return_value = [{"items": [{"type": "Page", "page_url": "outline", "title": "Outline"}]}]
        result = _collect_module_page_candidates(101, mock_client)
        assert result[0]["page_slug"] == "outline"

    def test_collect_frontpage_page_candidates(self):
        from api.integrations.syllabus import _collect_frontpage_page_candidates
        mock_client = MagicMock()
        mock_client.get_front_page.return_value = {"body": '<a href="/courses/101/pages/course-outline">Outline</a>'}
        result = _collect_frontpage_page_candidates(101, mock_client)
        assert result[0]["page_slug"] == "course-outline"

    def test_page_collectors_cover_exceptions_and_duplicate_skips(self):
        from api.integrations.syllabus import (
            _collect_syllabus_body_page_candidates,
            _collect_module_page_candidates,
            _collect_frontpage_page_candidates,
        )
        mock_client = MagicMock()
        mock_client.get_syllabus.side_effect = Exception("boom")
        mock_client.get_course_modules.side_effect = Exception("boom")
        mock_client.get_front_page.side_effect = Exception("boom")
        assert _collect_syllabus_body_page_candidates(101, mock_client) == []
        assert _collect_module_page_candidates(101, mock_client) == []
        assert _collect_frontpage_page_candidates(101, mock_client) == []

        mock_client = MagicMock()
        mock_client.get_syllabus.return_value = {"syllabus_body": '<a href="/courses/101/pages/p1">One</a><a href="/courses/101/pages/p1">Dup</a>'}
        mock_client.get_course_modules.return_value = [{"items": [{"type": "Page", "page_url": "p2", "title": "Two"}, {"type": "Page", "page_url": "p2", "title": "Dup"}, {"type": "Assignment"}]}]
        mock_client.get_front_page.return_value = {"body": '<a href="/courses/101/pages/p3">Three</a><a href="/courses/101/pages/p3">Dup</a>'}
        assert len(_collect_syllabus_body_page_candidates(101, mock_client)) == 1
        assert len(_collect_module_page_candidates(101, mock_client)) == 1
        assert len(_collect_frontpage_page_candidates(101, mock_client)) == 1


# ── find_syllabus_file ────────────────────────────────────────────────────────

class TestFindSyllabusFile:
    def test_returns_none_when_no_candidates(self):
        from api.integrations.syllabus import find_syllabus_file
        mock_client = MagicMock()
        mock_client.get_course_files.return_value = []
        mock_client.get_course_modules.return_value = []
        assert find_syllabus_file(101, mock_client) is None

    def test_returns_high_confidence_url_directly(self):
        from api.integrations.syllabus import find_syllabus_file
        mock_client = MagicMock()
        # A file named "syllabus.pdf" has high keyword confidence
        mock_client.get_course_files.return_value = [
            {"display_name": "syllabus.pdf", "url": "http://a/syllabus.pdf"},
        ]
        mock_client.get_course_modules.return_value = []
        url = find_syllabus_file(101, mock_client)
        assert url == "http://a/syllabus.pdf"

    def test_returns_best_url_immediately_when_top_confidence_exceeds_threshold(self):
        from api.integrations.syllabus import find_syllabus_file
        with patch("api.integrations.syllabus._collect_file_candidates", return_value=[{"name": "x", "url": "http://a/syllabus.pdf", "confidence": 1.0}]), \
             patch("api.integrations.syllabus._collect_module_candidates", return_value=[]):
            assert find_syllabus_file(101, MagicMock()) == "http://a/syllabus.pdf"

    def test_low_confidence_asks_claude(self):
        from api.integrations.syllabus import find_syllabus_file
        mock_client = MagicMock()
        mock_client.get_course_files.return_value = [
            {"display_name": "file_abc123.pdf", "url": "http://a/file.pdf"},
        ]
        mock_client.get_course_modules.return_value = []

        with patch("api.integrations.syllabus._ask_claude_pick_syllabus", return_value="http://a/file.pdf") as mock_pick:
            url = find_syllabus_file(101, mock_client)
        mock_pick.assert_called_once()
        assert url == "http://a/file.pdf"

    def test_deduplicates_urls_and_returns_high_confidence_best(self):
        from api.integrations.syllabus import find_syllabus_file
        mock_client = MagicMock()
        mock_client.get_course_files.return_value = [{"display_name": "syllabus.pdf", "url": "http://a/syllabus.pdf"}]
        mock_client.get_course_modules.return_value = [{"items": []}]
        with patch("api.integrations.syllabus._collect_module_candidates", return_value=[{"name": "duplicate.pdf", "url": "http://a/syllabus.pdf", "confidence": 0.0}]):
            assert find_syllabus_file(101, mock_client) == "http://a/syllabus.pdf"


# ── find_syllabus_frontpage ───────────────────────────────────────────────────

class TestFindSyllabusFrontpage:
    def test_returns_none_when_no_front_page(self):
        from api.integrations.syllabus import find_syllabus_frontpage
        mock_client = MagicMock()
        mock_client.get_front_page.side_effect = Exception("404")
        assert find_syllabus_frontpage(101, mock_client) is None

    def test_returns_none_when_no_body(self):
        from api.integrations.syllabus import find_syllabus_frontpage
        mock_client = MagicMock()
        mock_client.get_front_page.return_value = {"body": ""}
        assert find_syllabus_frontpage(101, mock_client) is None

    def test_returns_url_from_scored_link(self):
        from api.integrations.syllabus import find_syllabus_frontpage
        mock_client = MagicMock()
        mock_client.get_front_page.return_value = {
            "body": '<a href="/courses/101/files/42/download">Course Syllabus</a>',
        }
        mock_client.get_file_download_url.return_value = "http://a/syllabus.pdf"
        url = find_syllabus_frontpage(101, mock_client)
        assert url == "http://a/syllabus.pdf"

    def test_returns_none_when_no_matching_file_links(self):
        from api.integrations.syllabus import find_syllabus_frontpage
        mock_client = MagicMock()
        mock_client.get_front_page.return_value = {
            "body": '<a href="https://external.com/page">External link</a>',
        }
        assert find_syllabus_frontpage(101, mock_client) is None

    def test_returns_none_when_html_has_no_links(self):
        from api.integrations.syllabus import find_syllabus_frontpage
        mock_client = MagicMock()
        mock_client.get_front_page.return_value = {"body": "<p>No files here</p>"}
        assert find_syllabus_frontpage(101, mock_client) is None

    def test_picks_highest_scored_pdf_link(self):
        from api.integrations.syllabus import find_syllabus_frontpage
        mock_client = MagicMock()
        mock_client.get_front_page.return_value = {
            "body": (
                '<a href="/courses/101/files/41/download">Week 1 slides</a>'
                '<a href="/courses/101/files/42/download">Course Syllabus</a>'
            ),
        }
        mock_client.get_file_download_url.side_effect = ["http://a/slides.pdf", "http://a/syllabus.pdf"]
        assert find_syllabus_frontpage(101, mock_client) == "http://a/syllabus.pdf"

    def test_skips_bad_file_links_duplicates_and_resolution_errors(self):
        from api.integrations.syllabus import find_syllabus_frontpage
        mock_client = MagicMock()
        mock_client.get_front_page.return_value = {
            "body": (
                '<a href="/courses/101/download">No file id</a>'
                '<a href="/courses/101/files/42/download">Course Outline</a>'
                '<a href="/courses/101/files/42/download">Duplicate</a>'
                '<a href="/courses/101/files/43/download">Course Syllabus</a>'
            ),
        }
        mock_client.get_file_download_url.side_effect = [RuntimeError("nope"), "http://a/syllabus.pdf"]
        assert find_syllabus_frontpage(101, mock_client) == "http://a/syllabus.pdf"


# ── find_syllabus_page ────────────────────────────────────────────────────────

class TestFindSyllabusPage:
    def test_returns_none_when_no_candidates(self):
        from api.integrations.syllabus import find_syllabus_page
        mock_client = MagicMock()
        mock_client.get_syllabus.return_value = {"syllabus_body": ""}
        mock_client.get_course_modules.return_value = []
        mock_client.get_front_page.return_value = {"body": ""}
        assert find_syllabus_page(101, mock_client) is None

    def test_returns_best_candidate(self):
        from api.integrations.syllabus import find_syllabus_page
        mock_client = MagicMock()
        mock_client.get_syllabus.return_value = {
            "syllabus_body": '<a href="/courses/101/pages/course-syllabus">Course Syllabus</a>',
        }
        mock_client.get_course_modules.return_value = []
        mock_client.get_front_page.return_value = {"body": ""}
        result = find_syllabus_page(101, mock_client)
        assert result is not None
        assert result["page_slug"] == "course-syllabus"

    def test_returns_none_when_best_candidate_has_zero_confidence(self):
        from api.integrations.syllabus import find_syllabus_page
        with patch("api.integrations.syllabus._collect_syllabus_body_page_candidates", return_value=[{"page_slug": "x", "confidence": 0.0}]), \
             patch("api.integrations.syllabus._collect_module_page_candidates", return_value=[]), \
             patch("api.integrations.syllabus._collect_frontpage_page_candidates", return_value=[]):
            assert find_syllabus_page(101, MagicMock()) is None

    def test_skips_duplicate_slugs(self):
        from api.integrations.syllabus import find_syllabus_page
        dup = {"page_slug": "x", "confidence": 1.0}
        with patch("api.integrations.syllabus._collect_syllabus_body_page_candidates", return_value=[dup]), \
             patch("api.integrations.syllabus._collect_module_page_candidates", return_value=[dup]), \
             patch("api.integrations.syllabus._collect_frontpage_page_candidates", return_value=[]):
            assert find_syllabus_page(101, MagicMock())["page_slug"] == "x"


# ── PDF download and text extraction ─────────────────────────────────────────

class TestDownloadPdf:
    def test_returns_bytes_on_success(self):
        from api.integrations.syllabus import _download_pdf
        fake_bytes = b"%PDF-1.4 test content"
        mock_resp = MagicMock(ok=True, content=fake_bytes)
        with patch("api.integrations.syllabus.requests.get", return_value=mock_resp):
            result = _download_pdf("http://a/file.pdf")
        assert result == fake_bytes

    def test_raises_on_http_error(self):
        from api.integrations.syllabus import _download_pdf, SyllabusError
        mock_resp = MagicMock(ok=False, status_code=403)
        with patch("api.integrations.syllabus.requests.get", return_value=mock_resp):
            with pytest.raises(SyllabusError, match="403"):
                _download_pdf("http://a/file.pdf")


class TestExtractText:
    def test_raises_on_empty_pdf(self):
        from api.integrations.syllabus import _extract_text, SyllabusError
        mock_reader = MagicMock()
        mock_reader.pages = [MagicMock(extract_text=lambda: "")]
        with patch("api.integrations.syllabus.PdfReader", return_value=mock_reader):
            with pytest.raises(SyllabusError, match="no extractable text"):
                _extract_text(b"fake-pdf-bytes")

    def test_returns_text_from_pages(self):
        from api.integrations.syllabus import _extract_text
        page = MagicMock()
        page.extract_text.return_value = "Midterm: 40%\nFinal: 60%"
        mock_reader = MagicMock()
        mock_reader.pages = [page]
        with patch("api.integrations.syllabus.PdfReader", return_value=mock_reader):
            text = _extract_text(b"fake-pdf-bytes")
        assert "Midterm" in text

    def test_raises_syllabus_error_on_pypdf_exception(self):
        from api.integrations.syllabus import _extract_text, SyllabusError
        with patch("api.integrations.syllabus.PdfReader", side_effect=Exception("corrupt")):
            with pytest.raises(SyllabusError, match="pypdf could not read PDF"):
                _extract_text(b"bad-bytes")


# ── Claude LLM weight extraction ─────────────────────────────────────────────

class TestAskClaude:
    def _make_claude_response(self, text: str):
        msg = MagicMock()
        msg.content = [MagicMock(text=text)]
        return msg

    def test_returns_parsed_weights(self):
        from api.integrations.syllabus import _ask_claude
        fake_response = self._make_claude_response('{"Midterm": 40, "Final": 60}')
        mock_client = MagicMock()
        mock_client.messages.create.return_value = fake_response
        with patch("api.integrations.syllabus._get_anthropic_client", return_value=mock_client):
            result = _ask_claude("Midterm 40%, Final 60%")
        assert result == {"Midterm": 40, "Final": 60}

    def test_strips_markdown_fences(self):
        from api.integrations.syllabus import _ask_claude
        raw = '```json\n{"Assignments": 30, "Final": 70}\n```'
        fake_response = self._make_claude_response(raw)
        mock_client = MagicMock()
        mock_client.messages.create.return_value = fake_response
        with patch("api.integrations.syllabus._get_anthropic_client", return_value=mock_client):
            result = _ask_claude("some syllabus text")
        assert result["Assignments"] == 30

    def test_raises_on_invalid_json(self):
        from api.integrations.syllabus import _ask_claude, SyllabusError
        fake_response = self._make_claude_response("not valid json at all")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = fake_response
        with patch("api.integrations.syllabus._get_anthropic_client", return_value=mock_client):
            with pytest.raises(SyllabusError, match="non-JSON"):
                _ask_claude("some text")

    def test_raises_on_non_dict_response(self):
        from api.integrations.syllabus import _ask_claude, SyllabusError
        fake_response = self._make_claude_response("[1, 2, 3]")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = fake_response
        with patch("api.integrations.syllabus._get_anthropic_client", return_value=mock_client):
            with pytest.raises(SyllabusError, match="Expected a JSON object"):
                _ask_claude("some text")

    def test_allows_weights_that_do_not_sum_to_100(self):
        from api.integrations.syllabus import _ask_claude
        fake_response = self._make_claude_response('{"Assignments": 40, "Final": 40}')
        mock_client = MagicMock()
        mock_client.messages.create.return_value = fake_response
        with patch("api.integrations.syllabus._get_anthropic_client", return_value=mock_client):
            result = _ask_claude("some syllabus text")
        assert sum(result.values()) == 80


# ── parse_syllabus_weights full pipeline ─────────────────────────────────────

class TestParseSyllabusWeights:
    def test_cache_hit_returns_cached(self):
        from api.integrations.syllabus import _parse_syllabus_weights_cached
        cached = {"Midterm": 40.0, "Final": 60.0}
        with patch("api.integrations.syllabus._load_persisted_weights", return_value=cached):
            source, weights = _parse_syllabus_weights_cached(
                101, "key", MagicMock(), pdf_url="http://a/file.pdf"
            )
        assert weights == cached
        assert source == "http://a/file.pdf"

    def test_pdf_url_path_downloads_and_parses(self):
        from api.integrations.syllabus import _parse_syllabus_weights_cached
        expected_weights = {"Final Exam": 50, "Assignments": 50}
        with patch("api.integrations.syllabus._load_persisted_weights", return_value=None), \
             patch("api.integrations.syllabus._download_pdf", return_value=b"bytes") as mock_dl, \
             patch("api.integrations.syllabus._extract_text", return_value="text") as mock_ext, \
             patch("api.integrations.syllabus._ask_claude", return_value=expected_weights) as mock_ask, \
             patch("api.integrations.syllabus._save_persisted_weights"):
            source, weights = _parse_syllabus_weights_cached(
                101, "key", MagicMock(), pdf_url="http://a/file.pdf"
            )
        mock_dl.assert_called_once_with("http://a/file.pdf")
        mock_ext.assert_called_once()
        mock_ask.assert_called_once()
        assert weights == expected_weights

    def test_no_source_raises_syllabus_error(self):
        from api.integrations.syllabus import _parse_syllabus_weights_cached, SyllabusError
        mock_client = MagicMock()
        with patch("api.integrations.syllabus.find_syllabus_file", return_value=None), \
             patch("api.integrations.syllabus.find_syllabus_frontpage", return_value=None), \
             patch("api.integrations.syllabus.find_syllabus_page", return_value=None):
            with pytest.raises(SyllabusError):
                _parse_syllabus_weights_cached(101, "key", mock_client)

    def test_syllabus_body_html_fallback(self):
        from api.integrations.syllabus import _parse_syllabus_weights_cached
        expected_weights = {"Quiz": 20, "Exam": 80}
        mock_client = MagicMock()
        with patch("api.integrations.syllabus.find_syllabus_file", return_value=None), \
             patch("api.integrations.syllabus.find_syllabus_frontpage", return_value=None), \
             patch("api.integrations.syllabus.find_syllabus_page", return_value=None), \
             patch("api.integrations.syllabus._load_persisted_weights", return_value=None), \
             patch("api.integrations.syllabus._extract_text_from_html", return_value="text"), \
             patch("api.integrations.syllabus._ask_claude", return_value=expected_weights), \
             patch("api.integrations.syllabus._save_persisted_weights"):
            source, weights = _parse_syllabus_weights_cached(
                101, "key", mock_client,
                syllabus_body_html="<p>Quiz 20%, Exam 80%</p>",
            )
        assert weights == expected_weights
        assert source == "syllabus-body:101"

    def test_canvas_page_fallback(self):
        from api.integrations.syllabus import _parse_syllabus_weights_cached
        page_candidate = {"page_slug": "course-outline", "confidence": 0.4}
        expected_weights = {"Midterm": 50, "Final": 50}
        mock_client = MagicMock()
        mock_client.get_page.return_value = {"body": "<p>content</p>"}
        with patch("api.integrations.syllabus.find_syllabus_file", return_value=None), \
             patch("api.integrations.syllabus.find_syllabus_frontpage", return_value=None), \
             patch("api.integrations.syllabus.find_syllabus_page", return_value=page_candidate), \
             patch("api.integrations.syllabus._load_persisted_weights", return_value=None), \
             patch("api.integrations.syllabus._extract_text_from_html", return_value="text"), \
             patch("api.integrations.syllabus._ask_claude", return_value=expected_weights), \
             patch("api.integrations.syllabus._save_persisted_weights"):
            source, weights = _parse_syllabus_weights_cached(101, "key", mock_client)
        assert weights == expected_weights
        assert "canvas-page" in source

    def test_canvas_page_cache_hit(self):
        from api.integrations.syllabus import _parse_syllabus_weights_cached
        page_candidate = {"page_slug": "course-outline", "confidence": 0.4}
        cached = {"Midterm": 50, "Final": 50}
        mock_client = MagicMock()
        with patch("api.integrations.syllabus.find_syllabus_file", return_value=None), \
             patch("api.integrations.syllabus.find_syllabus_frontpage", return_value=None), \
             patch("api.integrations.syllabus.find_syllabus_page", return_value=page_candidate), \
             patch("api.integrations.syllabus._load_persisted_weights", return_value=cached):
            source, weights = _parse_syllabus_weights_cached(101, "key", mock_client)
        assert weights == cached

    def test_docx_source_flows_through_same_download_parse_pipeline(self):
        from api.integrations.syllabus import _parse_syllabus_weights_cached
        with patch("api.integrations.syllabus._load_persisted_weights", return_value=None), \
             patch("api.integrations.syllabus._download_pdf", return_value=b"docx-bytes") as mock_dl, \
             patch("api.integrations.syllabus._extract_text", return_value="Assignments 100%"), \
             patch("api.integrations.syllabus._ask_claude", return_value={"Assignments": 100}), \
             patch("api.integrations.syllabus._save_persisted_weights"):
            source, weights = _parse_syllabus_weights_cached(
                101, "key", MagicMock(), pdf_url="http://a/syllabus.docx"
            )
        mock_dl.assert_called_once_with("http://a/syllabus.docx")
        assert source.endswith(".docx")
        assert weights["Assignments"] == 100


class TestPersistedWeightsHelpers:
    def test_save_persisted_weights_swallows_cache_error(self):
        from api.integrations.syllabus import _save_persisted_weights
        from api.integrations.syllabus_cache import SyllabusCacheError
        with patch("api.integrations.syllabus.save_cached_syllabus_weights", side_effect=SyllabusCacheError("fail")):
            _save_persisted_weights(101, "src", {"Midterm": 40})

    def test_load_persisted_weights_returns_none_on_cache_error(self):
        from api.integrations.syllabus import _load_persisted_weights
        from api.integrations.syllabus_cache import SyllabusCacheError
        with patch("api.integrations.syllabus.get_cached_syllabus_weights", side_effect=SyllabusCacheError("fail")):
            assert _load_persisted_weights(101, "src") is None

    def test_get_anthropic_client_requires_key(self, monkeypatch):
        from api.integrations.syllabus import _get_anthropic_client, SyllabusError
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(SyllabusError, match="ANTHROPIC_API_KEY"):
            _get_anthropic_client()


# ── ask_claude_pick_syllabus ──────────────────────────────────────────────────

class TestAskClaudePickSyllabus:
    def _claude_response(self, text: str):
        msg = MagicMock()
        msg.content = [MagicMock(text=text)]
        return msg

    def test_returns_matching_url(self):
        from api.integrations.syllabus import _ask_claude_pick_syllabus
        candidates = [
            {"name": "syllabus.pdf", "label": "syllabus.pdf", "url": "http://a/syllabus.pdf", "confidence": 0.1},
            {"name": "notes.pdf",    "label": "notes.pdf",    "url": "http://a/notes.pdf",    "confidence": 0.0},
        ]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._claude_response("syllabus.pdf")
        with patch("api.integrations.syllabus._get_anthropic_client", return_value=mock_client):
            result = _ask_claude_pick_syllabus(candidates)
        assert result == "http://a/syllabus.pdf"

    def test_returns_none_when_claude_says_none(self):
        from api.integrations.syllabus import _ask_claude_pick_syllabus
        candidates = [
            {"name": "file.pdf", "label": "file.pdf", "url": "http://a/file.pdf", "confidence": 0.0},
        ]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._claude_response("none")
        with patch("api.integrations.syllabus._get_anthropic_client", return_value=mock_client):
            result = _ask_claude_pick_syllabus(candidates)
        assert result is None


class TestSyllabusAdditional:
    def test_get_anthropic_client_builds_client(self, monkeypatch):
        from api.integrations.syllabus import _get_anthropic_client
        fake = object()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        with patch("api.integrations.syllabus.anthropic.Anthropic", return_value=fake) as mock_ctor:
            result = _get_anthropic_client()
        assert result is fake
        mock_ctor.assert_called_once_with(api_key="test-key")

    def test_collect_file_candidates_uses_filename_fallback(self):
        from api.integrations.syllabus import _collect_file_candidates
        mock_client = MagicMock()
        mock_client.get_course_files.return_value = [{"filename": "outline.pdf", "url": "http://a/outline.pdf"}]
        result = _collect_file_candidates(101, mock_client)
        assert result[0]["filename"] == "outline.pdf"

    def test_collect_module_candidates_skips_missing_url_and_bad_extension(self):
        from api.integrations.syllabus import _collect_module_candidates
        mock_client = MagicMock()
        mock_client.get_course_modules.return_value = [{"items": [{"type": "File", "content_id": 1, "title": "Outline"}]}]
        mock_client.get_file_metadata.return_value = {"display_name": "outline.txt", "url": None}
        assert _collect_module_candidates(101, mock_client) == []

    def test_ask_claude_pick_syllabus_fuzzy_matches_label(self):
        from api.integrations.syllabus import _ask_claude_pick_syllabus
        candidates = [{"name": "outline.pdf", "label": "outline.pdf (module: Course Outline)", "url": "http://a/outline.pdf", "confidence": 0.1}]
        mock_client = MagicMock()
        mock_client.messages.create.return_value.content = [MagicMock(text="Course Outline")]
        with patch("api.integrations.syllabus._get_anthropic_client", return_value=mock_client):
            assert _ask_claude_pick_syllabus(candidates) == "http://a/outline.pdf"

    def test_extract_text_from_html_raises_on_empty(self):
        from api.integrations.syllabus import _extract_text_from_html, SyllabusError
        with pytest.raises(SyllabusError, match="no extractable text"):
            _extract_text_from_html("<div>   </div>")

    def test_load_persisted_weights_returns_cached_value(self):
        from api.integrations.syllabus import _load_persisted_weights
        with patch("api.integrations.syllabus.get_cached_syllabus_weights", return_value={"Midterm": 40.0}):
            assert _load_persisted_weights(101, "src") == {"Midterm": 40.0}

    def test_parse_syllabus_weights_wrapper_uses_client_cache_key(self):
        from api.integrations.syllabus import parse_syllabus_weights
        mock_client = MagicMock()
        mock_client._token_cache_key = "cache-key"
        with patch("api.integrations.syllabus._parse_syllabus_weights_cached", return_value=("src", {"Midterm": 40.0})) as mock_cached:
            result = parse_syllabus_weights(101, mock_client)
        assert result == ("src", {"Midterm": 40.0})
        assert mock_cached.call_args.args[1] == "cache-key"

    def test_parse_syllabus_weights_wrapper_default_cache_key(self):
        from api.integrations.syllabus import parse_syllabus_weights
        class ClientWithoutCacheKey:
            pass
        mock_client = ClientWithoutCacheKey()
        with patch("api.integrations.syllabus._parse_syllabus_weights_cached", return_value=("src", {"Midterm": 40.0})) as mock_cached:
            parse_syllabus_weights(101, mock_client)
        assert mock_cached.call_args.args[1] == "default"

    def test_returns_none_when_no_match(self):
        from api.integrations.syllabus import _ask_claude_pick_syllabus
        candidates = [
            {"name": "abc123xyz.pdf", "label": "abc123xyz.pdf", "url": "http://a/abc123xyz.pdf", "confidence": 0.0},
        ]
        mock_client = MagicMock()
        # Response that shares no substring with "abc123xyz.pdf" and is not "none"
        mock_client.messages.create.return_value.content = [MagicMock(text="qqqqqqqq.pdf")]
        with patch("api.integrations.syllabus._get_anthropic_client", return_value=mock_client):
            result = _ask_claude_pick_syllabus(candidates)
        assert result is None

    def test_ask_claude_pick_syllabus_exact_name_match(self):
        from api.integrations.syllabus import _ask_claude_pick_syllabus
        candidates = [
            {"name": "syllabus.pdf", "label": "Course Syllabus", "url": "http://a/syllabus.pdf", "confidence": 0.1},
        ]
        mock_client = MagicMock()
        mock_client.messages.create.return_value.content = [MagicMock(text="syllabus.pdf")]
        with patch("api.integrations.syllabus._get_anthropic_client", return_value=mock_client):
            result = _ask_claude_pick_syllabus(candidates)
        assert result == "http://a/syllabus.pdf"

    def test_ask_claude_pick_syllabus_name_substring_match(self):
        from api.integrations.syllabus import _ask_claude_pick_syllabus
        candidates = [
            {"name": "course-syllabus.pdf", "label": "Document", "url": "http://a/syllabus.pdf", "confidence": 0.1},
        ]
        mock_client = MagicMock()
        mock_client.messages.create.return_value.content = [MagicMock(text="syllabus")]
        with patch("api.integrations.syllabus._get_anthropic_client", return_value=mock_client):
            result = _ask_claude_pick_syllabus(candidates)
        assert result == "http://a/syllabus.pdf"

    def test_extract_text_from_html_success_and_save_persisted_weights_success(self):
        from api.integrations.syllabus import _extract_text_from_html, _save_persisted_weights
        assert _extract_text_from_html("<p>Midterm</p><p>40%</p>") == "Midterm\n40%"
        with patch("api.integrations.syllabus.save_cached_syllabus_weights") as mock_save:
            _save_persisted_weights(101, "src", {"Midterm": 40.0})
        mock_save.assert_called_once()

    def test_parse_syllabus_weights_cached_syllabus_body_cache_hit(self):
        from api.integrations.syllabus import _parse_syllabus_weights_cached
        with patch("api.integrations.syllabus.find_syllabus_file", return_value=None), \
             patch("api.integrations.syllabus.find_syllabus_frontpage", return_value=None), \
             patch("api.integrations.syllabus.find_syllabus_page", return_value=None), \
             patch("api.integrations.syllabus._load_persisted_weights", return_value={"Midterm": 40.0}):
            source, weights = _parse_syllabus_weights_cached(101, "key", MagicMock(), syllabus_body_html="<p>x</p>")
        assert source == "syllabus-body:101"
        assert weights == {"Midterm": 40.0}
