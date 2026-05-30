"""Tests for internal scraper link extraction functions.

Tests _extract_links, _extract_subject_period_from_rules, _matches_extensions,
and _subject_period_source_value from function_app/src/scraper.py.
"""

from __future__ import annotations

from function_app.src.models import ScrapeStep, SubjectPeriodRuleItem
from function_app.src.scraper import (
    _extract_links,
    _extract_subject_period_from_rules,
    _matches_extensions,
    _subject_period_source_value,
)

# ---------------------------------------------------------------------------
# _matches_extensions
# ---------------------------------------------------------------------------


class TestMatchesExtensions:
    def test_no_extensions_matches_anything(self):
        assert _matches_extensions("https://example.com/file.pdf", []) is True
        assert _matches_extensions("https://example.com/file", []) is True

    def test_matching_extension(self):
        assert _matches_extensions("https://example.com/data.csv", ["csv"]) is True

    def test_non_matching_extension(self):
        assert _matches_extensions("https://example.com/data.pdf", ["csv"]) is False

    def test_case_insensitive_extension_check(self):
        assert _matches_extensions("https://example.com/data.CSV", ["csv"]) is True

    def test_multiple_extensions(self):
        assert (
            _matches_extensions("https://example.com/data.xlsx", ["csv", "xlsx"])
            is True
        )
        assert (
            _matches_extensions("https://example.com/data.pdf", ["csv", "xlsx"])
            is False
        )


# ---------------------------------------------------------------------------
# _subject_period_source_value
# ---------------------------------------------------------------------------


class TestSubjectPeriodSourceValue:
    def test_file_name_source(self):
        val = _subject_period_source_value(
            "file_name", "Link text", "https://example.com/data_march2026.csv", ""
        )
        assert val == "data_march2026.csv"

    def test_filename_alias(self):
        val = _subject_period_source_value(
            "filename", "Link text", "https://example.com/data_march2026.csv", ""
        )
        assert val == "data_march2026.csv"

    def test_url_segment_source(self):
        url = "https://example.com/march-2026/data.csv"
        val = _subject_period_source_value("url_segment", "Link", url, "")
        assert val == url

    def test_page_text_source(self):
        page_text = "Data for March 2026"
        val = _subject_period_source_value(
            "page_text", "Link", "https://x.com/f.csv", page_text
        )
        assert val == page_text

    def test_page_elements_alias(self):
        page_text = "Data for March 2026"
        val = _subject_period_source_value(
            "page_elements", "Link", "https://x.com/f.csv", page_text
        )
        assert val == page_text

    def test_link_text_source(self):
        val = _subject_period_source_value(
            "link_text", "March 2026 data", "https://x.com/f.csv", ""
        )
        assert val == "March 2026 data"

    def test_unknown_source_falls_back_to_link_text(self):
        val = _subject_period_source_value(
            "unknown", "March 2026", "https://x.com/f.csv", ""
        )
        assert val == "March 2026"


# ---------------------------------------------------------------------------
# _extract_subject_period_from_rules
# ---------------------------------------------------------------------------


class TestExtractSubjectPeriodFromRules:
    def test_matches_first_rule(self):
        rules = [
            SubjectPeriodRuleItem(source="link_text", pattern=r"(March 2026)"),
        ]
        result = _extract_subject_period_from_rules(rules, "March 2026 report", "", "")
        assert result == "202603"

    def test_falls_through_to_second_rule(self):
        rules = [
            SubjectPeriodRuleItem(source="link_text", pattern=r"(never_matches_\d+)"),
            SubjectPeriodRuleItem(source="url_segment", pattern=r"(march-2026)"),
        ]
        result = _extract_subject_period_from_rules(
            rules, "Some text", "https://example.com/march-2026/file.csv", ""
        )
        assert result == "202603"

    def test_returns_none_when_no_rule_matches(self):
        rules = [
            SubjectPeriodRuleItem(source="link_text", pattern=r"(never_matches_\d+)"),
        ]
        result = _extract_subject_period_from_rules(rules, "no match", "", "")
        assert result is None

    def test_file_name_rule(self):
        rules = [
            SubjectPeriodRuleItem(source="file_name", pattern=r"(March-2026)"),
        ]
        result = _extract_subject_period_from_rules(
            rules, "", "https://example.com/March-2026-data.csv", ""
        )
        assert result == "202603"

    def test_page_text_rule(self):
        rules = [
            SubjectPeriodRuleItem(source="page_text", pattern=r"(March 2026)"),
        ]
        result = _extract_subject_period_from_rules(
            rules, "", "", "Data published for March 2026"
        )
        assert result == "202603"


# ---------------------------------------------------------------------------
# _extract_links
# ---------------------------------------------------------------------------


class TestExtractLinks:
    BASE_URL = "https://example.com/stats/"

    def _make_html(self, links: list[tuple[str, str]]) -> str:
        anchors = "\n".join(f'<a href="{href}">{text}</a>' for href, text in links)
        return f"<html><body>{anchors}</body></html>"

    def test_basic_link_extraction(self):
        html = self._make_html([("/data/march-2026.csv", "March 2026 data")])
        step = ScrapeStep(link_selector="a[href]")
        links = _extract_links(self.BASE_URL, html, step)
        assert len(links) == 1
        url, text, _, _ = links[0]
        assert url == "https://example.com/data/march-2026.csv"
        assert text == "March 2026 data"

    def test_resolves_relative_urls(self):
        html = self._make_html([("../other/file.csv", "File")])
        step = ScrapeStep(link_selector="a[href]")
        links = _extract_links(self.BASE_URL, html, step)
        assert links[0][0] == "https://example.com/other/file.csv"

    def test_css_selector_filters_links(self):
        html = """
        <html><body>
            <a href="/a.csv" class="download">A</a>
            <a href="/b.csv">B</a>
        </body></html>
        """
        step = ScrapeStep(link_selector="a.download[href]")
        links = _extract_links(self.BASE_URL, html, step)
        assert len(links) == 1
        assert "/a.csv" in links[0][0]

    def test_text_filter_excludes_non_matching(self):
        html = self._make_html(
            [
                ("/a.csv", "March 2026 Monthly data"),
                ("/b.csv", "Annual Report 2025"),
            ]
        )
        step = ScrapeStep(link_selector="a[href]", text_filter="Monthly")
        links = _extract_links(self.BASE_URL, html, step)
        assert len(links) == 1
        assert "March 2026" in links[0][1]

    def test_text_filter_is_case_insensitive(self):
        html = self._make_html([("/a.csv", "monthly report")])
        step = ScrapeStep(link_selector="a[href]", text_filter="Monthly")
        links = _extract_links(self.BASE_URL, html, step)
        assert len(links) == 1

    def test_text_filter_excludes_all_when_none_match(self):
        html = self._make_html([("/a.csv", "Annual 2025"), ("/b.csv", "Weekly")])
        step = ScrapeStep(link_selector="a[href]", text_filter="Monthly")
        links = _extract_links(self.BASE_URL, html, step)
        assert links == []

    def test_extension_filter(self):
        html = self._make_html(
            [("/a.csv", "CSV file"), ("/b.xlsx", "Excel file"), ("/c.pdf", "PDF")]
        )
        step = ScrapeStep(link_selector="a[href]", file_extensions=["csv", "xlsx"])
        links = _extract_links(self.BASE_URL, html, step)
        urls = [link[0] for link in links]
        assert any(u.endswith(".csv") for u in urls)
        assert any(u.endswith(".xlsx") for u in urls)
        assert not any(u.endswith(".pdf") for u in urls)

    def test_combined_text_and_extension_filter(self):
        html = self._make_html(
            [
                ("/a.csv", "Monthly CSV data"),
                ("/b.xlsx", "Monthly Excel data"),
                ("/c.csv", "Annual CSV data"),
            ]
        )
        step = ScrapeStep(
            link_selector="a[href]", text_filter="Monthly", file_extensions=["csv"]
        )
        links = _extract_links(self.BASE_URL, html, step)
        assert len(links) == 1
        assert links[0][0].endswith(".csv")
        assert "Monthly" in links[0][1]

    def test_returns_page_text_in_tuple(self):
        html = (
            "<html><body>"
            "<p>Page content here</p>"
            "<a href='/f.csv'>File</a>"
            "</body></html>"
        )
        step = ScrapeStep(link_selector="a[href]")
        links = _extract_links(self.BASE_URL, html, step)
        _, _, _, page_text = links[0]
        assert "Page content here" in page_text

    def test_no_href_links_excluded(self):
        html = "<html><body><a>No href</a><a href='/f.csv'>With href</a></body></html>"
        step = ScrapeStep(link_selector="a")
        links = _extract_links(self.BASE_URL, html, step)
        assert len(links) == 1

    def test_page_publication_datetime_from_page_text(self):
        html = (
            "<html><body>"
            "<p>Last updated: 15 March 2026</p>"
            "<a href='/f.csv'>File</a>"
            "</body></html>"
        )
        step = ScrapeStep(link_selector="a[href]")
        links = _extract_links(self.BASE_URL, html, step)
        _, _, pub_datetime, _ = links[0]
        assert pub_datetime == "20260315T000000"

    def test_empty_html_returns_no_links(self):
        step = ScrapeStep(link_selector="a[href]")
        links = _extract_links(self.BASE_URL, "<html><body></body></html>", step)
        assert links == []
