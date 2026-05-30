"""Tests for function_app/src/datetime_utils.py.

Covers all format branches in normalize_datetime_value, fiscal year logic,
compact month-year, ordinal stripping, ISO variants, extract_page_publication_datetime,
normalize_subject_period_value, and extract_datetime_from_pattern.
"""

from __future__ import annotations

import pytest

from function_app.src.datetime_utils import (
    _strip_ordinal_suffixes,
    extract_datetime_from_pattern,
    extract_datetime_from_selectors,
    extract_page_publication_datetime,
    normalize_datetime_value,
    normalize_subject_period_value,
)

# ---------------------------------------------------------------------------
# _strip_ordinal_suffixes
# ---------------------------------------------------------------------------


class TestStripOrdinalSuffixes:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1st March 2026", "1 March 2026"),
            ("2nd April 2025", "2 April 2025"),
            ("3rd May 2024", "3 May 2024"),
            ("15th June 2023", "15 June 2023"),
            ("22nd July 2022", "22 July 2022"),
            ("March 2026", "March 2026"),  # no ordinal - unchanged
        ],
    )
    def test_strips_correctly(self, raw, expected):
        assert _strip_ordinal_suffixes(raw) == expected


# ---------------------------------------------------------------------------
# normalize_datetime_value — standard calendar formats
# ---------------------------------------------------------------------------


class TestNormalizeDatetimeValueCalendar:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("March 2026", "20260301T000000"),
            ("Mar 2026", "20260301T000000"),
            ("15 March 2026", "20260315T000000"),
            ("15 Mar 2026", "20260315T000000"),
            ("1st March 2026", "20260301T000000"),
            ("15th June 2023", "20230615T000000"),
            ("3rd May 2024", "20240503T000000"),
            ("15 March 2026 10:30", "20260315T103000"),
            ("15 March 2026 10:30:45", "20260315T103045"),
        ],
    )
    def test_calendar_formats(self, value, expected):
        assert normalize_datetime_value(value) == expected


# ---------------------------------------------------------------------------
# normalize_datetime_value — ISO / compact formats
# ---------------------------------------------------------------------------


class TestNormalizeDatetimeValueIso:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("20260315T103045", "20260315T103045"),  # already compact ISO
            ("20260315", "20260315T000000"),  # compact date
            ("2026-03-15", "20260315T000000"),  # ISO date
            ("2026-03-15T10:30:45", "20260315T103045"),  # ISO datetime with T
            ("2026-03-15T10:30", "20260315T103000"),  # ISO datetime without seconds
        ],
    )
    def test_iso_formats(self, value, expected):
        assert normalize_datetime_value(value) == expected


# ---------------------------------------------------------------------------
# normalize_datetime_value — compact month-year (e.g. Mar26, Mar2026)
# ---------------------------------------------------------------------------


class TestNormalizeDatetimeValueCompactMonthYear:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("Mar26", "20260301T000000"),
            ("mar26", "20260301T000000"),
            ("MAR26", "20260301T000000"),
            ("Mar2026", "20260301T000000"),
            ("Jan25", "20250101T000000"),
            ("Dec24", "20241201T000000"),
            ("Sept26", "20260901T000000"),
        ],
    )
    def test_compact_formats(self, value, expected):
        assert normalize_datetime_value(value) == expected


# ---------------------------------------------------------------------------
# normalize_datetime_value — fiscal year format
# ---------------------------------------------------------------------------


class TestNormalizeDatetimeValueFiscalYear:
    @pytest.mark.parametrize(
        "value,expected",
        [
            # In FY 2025-26, Apr-Dec belong to 2025; Jan-Mar belong to 2026
            ("2025_26_march", "20260301T000000"),
            ("2025-26_march", "20260301T000000"),
            ("2025-26_january", "20260101T000000"),
            ("2025-26_april", "20250401T000000"),
            ("2025-26_december", "20251201T000000"),
            ("2024-25_march", "20250301T000000"),
            ("2024-25_august", "20240801T000000"),
        ],
    )
    def test_fiscal_year_formats(self, value, expected):
        assert normalize_datetime_value(value) == expected


# ---------------------------------------------------------------------------
# normalize_datetime_value — unparseable inputs
# ---------------------------------------------------------------------------


class TestNormalizeDatetimeValueUnparseable:
    @pytest.mark.parametrize(
        "value",
        [
            "",
            "not a date",
            "random text 12345",
            "99 Octember 2026",
        ],
    )
    def test_returns_none_for_unparseable(self, value):
        assert normalize_datetime_value(value) is None


# ---------------------------------------------------------------------------
# normalize_subject_period_value
# ---------------------------------------------------------------------------


class TestNormalizeSubjectPeriodValue:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("March 2026", "202603"),
            ("15 March 2026", "202603"),
            ("Mar26", "202603"),
            ("2026-03-15", "202603"),
        ],
    )
    def test_truncates_to_yyyymm(self, value, expected):
        assert normalize_subject_period_value(value) == expected

    def test_returns_none_for_unparseable(self):
        assert normalize_subject_period_value("not a date") is None


# ---------------------------------------------------------------------------
# extract_datetime_from_pattern
# ---------------------------------------------------------------------------


class TestExtractDatetimeFromPattern:
    def test_extracts_and_normalizes(self):
        result = extract_datetime_from_pattern(
            r"(March 2026)", "Performance March 2026"
        )
        assert result == "20260301T000000"

    def test_returns_none_when_no_match(self):
        result = extract_datetime_from_pattern(r"(March 2026)", "No date here")
        assert result is None

    def test_captures_group_in_match(self):
        result = extract_datetime_from_pattern(
            r"published\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
            "published 15 March 2026",
        )
        assert result == "20260315T000000"


# ---------------------------------------------------------------------------
# extract_page_publication_datetime
# ---------------------------------------------------------------------------


class TestExtractPagePublicationDatetime:
    @pytest.mark.parametrize(
        "page_text,expected",
        [
            ("Last updated: 15 May 2024", "20240515T000000"),
            ("Published: 1 January 2026", "20260101T000000"),
            ("Last updated: March 2026", "20260301T000000"),
            ("Last updated: 2026-03-15", "20260315T000000"),
            ("last updated: 15 March 2026 10:30", "20260315T103000"),
        ],
    )
    def test_extracts_publication_date(self, page_text, expected):
        assert extract_page_publication_datetime(page_text) == expected

    def test_returns_none_when_no_date_indicator(self):
        assert (
            extract_page_publication_datetime("Some page with no date signals") is None
        )

    def test_returns_none_for_empty_input(self):
        assert extract_page_publication_datetime("") is None

    def test_prefers_published_over_raw_date(self):
        # Should match "Published" keyword rather than free-floating dates
        text = "Data from 2020. Published: March 2026"
        result = extract_page_publication_datetime(text)
        assert result == "20260301T000000"


# ---------------------------------------------------------------------------
# extract_datetime_from_selectors
# ---------------------------------------------------------------------------


class TestExtractDatetimeFromSelectors:
    def test_returns_first_matching_selector(self):
        selectors = [
            r"(?:published)\s*:?\s*(\d{4}-\d{2}-\d{2})",
            r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        ]
        text = "published: 2026-03-15 Some other date 1 April 2026"
        result = extract_datetime_from_selectors(text, selectors)
        assert result == "20260315T000000"

    def test_returns_none_if_no_selector_matches(self):
        selectors = [r"(never matches \d+)"]
        result = extract_datetime_from_selectors("no match here", selectors)
        assert result is None

    def test_falls_through_to_second_selector(self):
        selectors = [
            r"(never matches \d+)",
            r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        ]
        result = extract_datetime_from_selectors("15 March 2026", selectors)
        assert result == "20260315T000000"
