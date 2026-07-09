"""
tests/test_acorn_pdf_parser.py — tests for api/integrations/acorn_pdf_parser.py
"""

import io
import pytest
from unittest.mock import MagicMock, patch

from api.integrations.acorn_pdf_parser import (
    AcornPdfParseError,
    parse_acorn_pdf,
    _parse_first_course_line,
    _parse_course_table,
    _parse_programs,
    _parse_term_block,
    _handle_continuation,
    _extract_text,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_pdf_bytes(page_texts):
    """Build a minimal fake PDF. We mock PdfReader so the bytes don't matter."""
    return b"%PDF-fake"


def _mock_reader(page_texts):
    reader = MagicMock()
    pages = []
    for text in page_texts:
        page = MagicMock()
        page.extract_text.return_value = text
        pages.append(page)
    reader.pages = pages
    return reader


# ── _extract_text ─────────────────────────────────────────────────────────────

class TestExtractText:
    def test_joins_pages(self):
        with patch("api.integrations.acorn_pdf_parser.PdfReader") as mock_cls:
            mock_cls.return_value = _mock_reader(["page 1", "page 2"])
            result = _extract_text(b"fake")
            assert "page 1" in result
            assert "page 2" in result

    def test_raises_on_invalid_pdf(self):
        with patch("api.integrations.acorn_pdf_parser.PdfReader", side_effect=Exception("bad")):
            with pytest.raises(AcornPdfParseError, match="Could not read PDF"):
                _extract_text(b"not a pdf")


# ── _parse_first_course_line ──────────────────────────────────────────────────

class TestParseFirstCourseLine:
    def test_standard_course(self):
        tokens = "CSCA08H3 Introduction to Computer Science I 0.50 84 A- B-".split()
        result = _parse_first_course_line(tokens, "2022 Fall")
        assert result["courseCode"] == "CSCA08H3"
        assert result["title"] == "Introduction to Computer Science I"
        assert result["credits"] == "0.50"
        assert result["mark"] == "84"
        assert result["grade"] == "A-"
        assert result["courseAverage"] == "B-"
        assert result["term"] == "2022 Fall"

    def test_cop_course(self):
        tokens = "COPB50H3 Foundations for Success 0.00 CR".split()
        result = _parse_first_course_line(tokens, "2022 Fall")
        assert result["courseCode"] == "COPB50H3"
        assert result["credits"] == "0.00"
        assert result["mark"] is None
        assert result["grade"] == "CR"

    def test_cr_non_cop_with_zero_credits_override(self):
        tokens = "PHLA11H3 Introduction to Ethics 0.00 CR".split()
        result = _parse_first_course_line(tokens, "2024 Fall")
        assert result["credits"] == "0.50"
        assert result["grade"] == "CR"

    def test_transfer_credit(self):
        tokens = "CSCA*** Transfer Credit - Equivalent 0.50".split()
        result = _parse_first_course_line(tokens, None)
        assert result["courseCode"] == "CSCA***"
        assert result["title"] == "Transfer Credit - Equivalent"
        assert result["credits"] == "0.50"
        assert result["grade"] is None
        assert result["term"] is None

    def test_transfer_with_grade_code(self):
        tokens = "CSCA*** Transfer Credit - Equivalent 0.50 A08".split()
        result = _parse_first_course_line(tokens, None)
        assert result["grade"] == "A08"

    def test_st_george_course_code(self):
        tokens = "CSC490H1 Capstone Design Proj 0.50 85 A A-".split()
        result = _parse_first_course_line(tokens, "2025 Fall")
        assert result["courseCode"] == "CSC490H1"
        assert result["mark"] == "85"
        assert result["grade"] == "A"
        assert result["courseAverage"] == "A-"

    def test_no_credit_returns_fallback(self):
        tokens = "CSCA08H3 Some Title Without Credits".split()
        result = _parse_first_course_line(tokens, "2022 Fall")
        assert result["credits"] is None
        assert result["title"] == "Some Title Without Credits"

    def test_cr_course_with_nonzero_credits(self):
        tokens = "STAD57H3 Time Series Analysis 0.50 CR C+".split()
        result = _parse_first_course_line(tokens, "2025 Fall")
        assert result["credits"] == "0.50"
        assert result["grade"] == "CR"
        assert result["courseAverage"] == "C+"

    def test_a_plus_grade(self):
        tokens = "STAC33H3 Applied Statistics 0.50 91 A+ B+".split()
        result = _parse_first_course_line(tokens, "2025 Winter")
        assert result["grade"] == "A+"
        assert result["courseAverage"] == "B+"
        assert result["mark"] == "91"


# ── _handle_continuation ─────────────────────────────────────────────────────

class TestHandleContinuation:
    def test_regular_course_appends_title(self):
        current = {"title": "Introduction to Computer", "_is_transfer": False}
        _handle_continuation(current, ["Science", "I"])
        assert current["title"] == "Introduction to Computer Science I"

    def test_transfer_picks_up_grade_code(self):
        current = {"title": "Transfer Credit", "grade": None, "_is_transfer": True}
        _handle_continuation(current, ["A08", "(BR=Quant)"])
        assert current["grade"] == "A08"
        assert current["title"] == "Transfer Credit"

    def test_transfer_no_grade_available(self):
        current = {"title": "Transfer Credit", "grade": None, "_is_transfer": True}
        _handle_continuation(current, ["(BR=SocBeh)"])
        assert current["grade"] is None


# ── _parse_course_table ───────────────────────────────────────────────────────

class TestParseCourseTable:
    def test_skips_structural_lines(self):
        lines = [
            "2022 Fall - Honours Bachelor of Science",
            "Sessional GPA   3.68  Cumulative GPA  3.68",
            "Status: Not assessed",
            "Crs Code  Title                        Wgt  Mrk  Grd  CrsAvg",
            "CSCA08H3  Introduction to CS I         0.50  84  A-     B-",
            "Credits Earned: 2.50",
        ]
        courses = _parse_course_table(lines, "2022 Fall")
        assert len(courses) == 1
        assert courses[0]["courseCode"] == "CSCA08H3"

    def test_multiline_title(self):
        lines = [
            "MATB41H3  Techniques of the Calculus of Several    0.50  74  B      C-",
            "          Variables I",
        ]
        courses = _parse_course_table(lines, "2023 Fall")
        assert len(courses) == 1
        assert courses[0]["title"] == "Techniques of the Calculus of Several Variables I"

    def test_multiple_courses(self):
        lines = [
            "CSCA08H3  Introduction to CS I         0.50  84  A-     B-",
            "CSCA67H3  Discrete Mathematics          0.50  78  B+     C+",
        ]
        courses = _parse_course_table(lines, "2022 Fall")
        assert len(courses) == 2
        assert courses[0]["courseCode"] == "CSCA08H3"
        assert courses[1]["courseCode"] == "CSCA67H3"

    def test_no_is_transfer_key_in_output(self):
        lines = [
            "CSCA08H3  Introduction to CS I         0.50  84  A-     B-",
        ]
        courses = _parse_course_table(lines, "2022 Fall")
        assert "_is_transfer" not in courses[0]


# ── _parse_term_block ─────────────────────────────────────────────────────────

class TestParseTermBlock:
    def test_extracts_gpa_and_status(self):
        lines = [
            "2022 Fall - Honours Bachelor of Science",
            "Sessional GPA   3.68  Cumulative GPA  3.68",
            "Status: Not assessed",
            "Crs Code  Title                        Wgt  Mrk  Grd  CrsAvg",
            "CSCA08H3  Introduction to CS I         0.50  84  A-     B-",
            "Credits Earned: 2.50",
        ]
        result = _parse_term_block(lines, "2022 Fall")
        assert result["term"] == "2022 Fall"
        assert result["sessionalGpa"] == 3.68
        assert result["cumulativeGpa"] == 3.68
        assert result["status"] == "Not assessed"
        assert len(result["courses"]) == 1

    def test_coop_term_no_gpa(self):
        lines = [
            "2024 Winter - Honours Bachelor of Science",
            "Crs Code  Title                        Wgt  Mrk  Grd  CrsAvg",
            "COPC01H3  Co-op work term              0.00      CR",
            "Credits Earned: 0.00",
        ]
        result = _parse_term_block(lines, "2024 Winter")
        assert result["sessionalGpa"] is None
        assert result["cumulativeGpa"] is None
        assert result["status"] is None
        assert len(result["courses"]) == 1

    def test_annual_gpa_line(self):
        lines = [
            "2023 Winter - Honours Bachelor of Science",
            "Sessional GPA   3.18  Annual GPA      3.43  Cumulative GPA  3.43",
            "Status: In good standing",
            "Crs Code  Title                        Wgt  Mrk  Grd  CrsAvg",
            "Credits Earned: 2.50",
        ]
        result = _parse_term_block(lines, "2023 Winter")
        assert result["sessionalGpa"] == 3.18
        assert result["cumulativeGpa"] == 3.43


# ── _parse_programs ───────────────────────────────────────────────────────────

class TestParsePrograms:
    def test_single_program(self):
        lines = [
            "Registration History",
            "2022 Fall-2026 Winter: University of Toronto Scarborough",
            "Honours Bachelor of Science Conferred - June 2026 with Distinction",
            "University of Toronto Scarborough",
            "Completed - 2026 Winter - Specialist (Co-operative) Program in",
            "Statistics- Statistical Machine Learning and Data Science Stream",
            "2023 Fall - Dean's List",
        ]
        programs = _parse_programs(lines)
        assert len(programs) == 1
        p = programs[0]
        assert p["enrollmentPeriod"] == "2022 Fall-2026 Winter"
        assert p["institution"] == "University of Toronto Scarborough"
        assert p["enrollmentStatus"] == "Completed"
        assert p["startSession"] == "2026 Winter"
        assert "Statistics-" in p["programName"]

    def test_in_progress_program(self):
        lines = [
            "2022 Fall-2026 Winter: University of Toronto Scarborough",
            "In Progress - 2023 Fall - Major Program in Computer Science",
        ]
        programs = _parse_programs(lines)
        assert len(programs) == 1
        assert programs[0]["enrollmentStatus"] == "In Progress"
        assert programs[0]["startSession"] == "2023 Fall"
        assert programs[0]["programName"] == "Major Program in Computer Science"

    def test_no_session_prefix(self):
        lines = [
            "2022 Fall-2026 Winter: UofT",
            "Completed - Some Program Without Session",
        ]
        programs = _parse_programs(lines)
        assert len(programs) == 1
        assert programs[0]["startSession"] is None
        assert programs[0]["programName"] == "Some Program Without Session"


# ── parse_acorn_pdf (integration) ─────────────────────────────────────────────

class TestParseAcornPdf:
    def test_empty_pdf_raises(self):
        with patch("api.integrations.acorn_pdf_parser.PdfReader") as mock_cls:
            mock_cls.return_value = _mock_reader([""])
            with pytest.raises(AcornPdfParseError, match="no extractable text"):
                parse_acorn_pdf(b"fake")

    def test_no_courses_raises(self):
        with patch("api.integrations.acorn_pdf_parser.PdfReader") as mock_cls:
            mock_cls.return_value = _mock_reader(["Complete Academic History\nJust some random text with no courses."])
            with pytest.raises(AcornPdfParseError, match="No courses or terms"):
                parse_acorn_pdf(b"fake")

    def test_missing_header_raises(self):
        with patch("api.integrations.acorn_pdf_parser.PdfReader") as mock_cls:
            mock_cls.return_value = _mock_reader(["Just some random PDF without the expected header."])
            with pytest.raises(AcornPdfParseError, match="does not appear to be an ACORN"):
                parse_acorn_pdf(b"fake")

    def test_single_term_pdf(self):
        text = (
            "Complete Academic History\n"
            "Registration History\n"
            "2022 Fall-2026 Winter: University of Toronto Scarborough\n"
            "In Progress - 2023 Fall - Major in Statistics\n"
            "Crs Code  Title           Wgt\n"
            "CSCA***   Transfer Credit 0.50\n"
            "Credits Earned: 0.50\n"
            "2022 Fall - Honours Bachelor of Science\n"
            "Sessional GPA   3.50  Cumulative GPA  3.50\n"
            "Status: In good standing\n"
            "Crs Code  Title           Wgt  Mrk  Grd  CrsAvg\n"
            "CSCA08H3  Intro to CS I   0.50  80   A-   B\n"
            "Credits Earned: 0.50\n"
        )
        with patch("api.integrations.acorn_pdf_parser.PdfReader") as mock_cls:
            mock_cls.return_value = _mock_reader([text])
            result = parse_acorn_pdf(b"fake")

        assert len(result["terms"]) == 1
        assert result["terms"][0]["term"] == "2022 Fall"
        assert result["terms"][0]["sessionalGpa"] == 3.50
        assert len(result["terms"][0]["courses"]) == 1

        transfer = [c for c in result["courses"] if c["term"] is None]
        assert len(transfer) == 1
        assert transfer[0]["courseCode"] == "CSCA***"

        assert len(result["programs"]) == 1
        assert result["programs"][0]["enrollmentStatus"] == "In Progress"

        assert result["source"] == "pdf"
        assert "importedAt" in result

    def test_deans_list_not_treated_as_term(self):
        text = (
            "Complete Academic History\n"
            "2022 Fall-2026 Winter: UofT\n"
            "2023 Fall - Dean's List\n"
            "2022 Fall - Honours Bachelor\n"
            "Crs Code  Title           Wgt  Mrk  Grd  CrsAvg\n"
            "CSCA08H3  Intro to CS     0.50  80   A-   B\n"
            "Credits Earned: 0.50\n"
        )
        with patch("api.integrations.acorn_pdf_parser.PdfReader") as mock_cls:
            mock_cls.return_value = _mock_reader([text])
            result = parse_acorn_pdf(b"fake")

        assert len(result["terms"]) == 1
        assert result["terms"][0]["term"] == "2022 Fall"

    def test_cop_corrections_applied(self):
        text = (
            "Complete Academic History\n"
            "2022 Fall - Honours Bachelor\n"
            "Crs Code  Title           Wgt  Mrk  Grd  CrsAvg\n"
            "COPB50H3  Co-op Found     0.00       CR\n"
            "Credits Earned: 0.00\n"
        )
        with patch("api.integrations.acorn_pdf_parser.PdfReader") as mock_cls:
            mock_cls.return_value = _mock_reader([text])
            result = parse_acorn_pdf(b"fake")

        cop = result["terms"][0]["courses"][0]
        assert cop["credits"] == "0.00"
        assert cop["mark"] is None
        assert cop["grade"] == "CR"

    def test_multipage_term_split(self):
        page1 = (
            "Complete Academic History\n"
            "2024 Fall - Honours Bachelor of Science\n"
        )
        page2 = (
            "Sessional GPA   3.60  Cumulative GPA  3.28\n"
            "Status: In good standing\n"
            "Crs Code  Title           Wgt  Mrk  Grd  CrsAvg\n"
            "CSCC37H3  Numerical Alg   0.50  83   A-   C+\n"
            "Credits Earned: 2.50\n"
        )
        with patch("api.integrations.acorn_pdf_parser.PdfReader") as mock_cls:
            mock_cls.return_value = _mock_reader([page1, page2])
            result = parse_acorn_pdf(b"fake")

        assert len(result["terms"]) == 1
        t = result["terms"][0]
        assert t["term"] == "2024 Fall"
        assert t["sessionalGpa"] == 3.60
        assert t["cumulativeGpa"] == 3.28
        assert len(t["courses"]) == 1


# ── integration with real sample PDF ─────────────────────────────────────────

class TestRealPdfIntegration:
    @pytest.fixture(autouse=True)
    def _load_sample(self):
        import os
        pdf_path = os.path.join(os.path.dirname(__file__), "..", "Academic History - ACORN.pdf")
        if not os.path.exists(pdf_path):
            pytest.skip("Sample PDF not available")
        with open(pdf_path, "rb") as f:
            self.result = parse_acorn_pdf(f.read())

    def test_term_count(self):
        assert len(self.result["terms"]) == 10

    def test_total_courses(self):
        assert len(self.result["courses"]) == 46

    def test_transfer_credits(self):
        transfers = [c for c in self.result["courses"] if c["term"] is None]
        assert len(transfers) == 5
        codes = [c["courseCode"] for c in transfers]
        assert codes.count("CSCA***") == 2
        assert codes.count("MATA***") == 2
        assert codes.count("MGEA***") == 1

    def test_programs(self):
        assert len(self.result["programs"]) == 1
        p = self.result["programs"][0]
        assert p["enrollmentPeriod"] == "2022 Fall-2026 Winter"
        assert p["institution"] == "University of Toronto Scarborough"
        assert p["enrollmentStatus"] == "Completed"
        assert p["startSession"] == "2026 Winter"
        assert "Specialist" in p["programName"]

    def test_first_term_gpa(self):
        fall_2022 = self.result["terms"][0]
        assert fall_2022["term"] == "2022 Fall"
        assert fall_2022["sessionalGpa"] == 3.68
        assert fall_2022["cumulativeGpa"] == 3.68
        assert fall_2022["status"] == "Not assessed"

    def test_last_term_gpa(self):
        winter_2026 = self.result["terms"][-1]
        assert winter_2026["term"] == "2026 Winter"
        assert winter_2026["sessionalGpa"] == 4.0
        assert winter_2026["cumulativeGpa"] == 3.43

    def test_cop_courses(self):
        cop = [c for c in self.result["courses"] if c["courseCode"].startswith("COP")]
        for c in cop:
            assert c["credits"] == "0.00"
            assert c["mark"] is None

    def test_st_george_course(self):
        csc490 = [c for c in self.result["courses"] if c["courseCode"] == "CSC490H1"]
        assert len(csc490) == 1
        assert csc490[0]["mark"] == "85"
        assert csc490[0]["grade"] == "A"

    def test_cr_course_nonzero_credits(self):
        phla = [c for c in self.result["courses"] if c["courseCode"] == "PHLA11H3"]
        assert len(phla) == 1
        assert phla[0]["credits"] == "0.50"
        assert phla[0]["grade"] == "CR"
        assert phla[0]["courseAverage"] == "B-"

    def test_no_is_transfer_key(self):
        for c in self.result["courses"]:
            assert "_is_transfer" not in c

    def test_source_is_pdf(self):
        assert self.result["source"] == "pdf"

    def test_coop_terms_no_gpa(self):
        coop_terms = [t for t in self.result["terms"] if t["term"] in ("2024 Winter", "2024 Summer", "2025 Summer")]
        assert len(coop_terms) == 3
        for t in coop_terms:
            assert t["sessionalGpa"] is None
            assert t["cumulativeGpa"] is None
