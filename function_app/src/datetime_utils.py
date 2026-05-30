from __future__ import annotations

import datetime as dt
import re
from typing import Optional


def now_utc_compact() -> str:
    """Return current UTC as YYYYMMDDTHHMMSS."""
    return dt.datetime.utcnow().strftime("%Y%m%dT%H%M%S")


def _strip_ordinal_suffixes(value: str) -> str:
    return re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", value, flags=re.IGNORECASE)


def normalize_datetime_value(value: str) -> Optional[str]:
    """Normalize a free-text date/datetime value into YYYYMMDDTHHMMSS.

    Uses midnight when only a date/month is present.
    """
    if not value:
        return None

    cleaned = " ".join(value.replace(",", " ").split())
    cleaned = _strip_ordinal_suffixes(cleaned)

    # Check exact compact-ISO formats BEFORE any dash replacement.
    if re.fullmatch(r"\d{8}T\d{6}", cleaned):
        return cleaned

    if re.fullmatch(r"\d{8}", cleaned):
        parsed = dt.datetime.strptime(cleaned, "%Y%m%d")
        return parsed.strftime("%Y%m%dT%H%M%S")

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", cleaned):
        parsed = dt.datetime.strptime(cleaned, "%Y-%m-%dT%H:%M:%S")
        return parsed.strftime("%Y%m%dT%H%M%S")

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", cleaned):
        parsed = dt.datetime.strptime(cleaned, "%Y-%m-%dT%H:%M")
        return parsed.strftime("%Y%m%dT%H%M%S")

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
        parsed = dt.datetime.strptime(cleaned, "%Y-%m-%d")
        return parsed.strftime("%Y%m%dT%H%M%S")

    # Check for fiscal_year_and_month format (e.g., "2025-26_march" -> "2025 26 march")
    fiscal_match = re.match(
        r"(\d{4})\s+(\d{2})\s+(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|september|oct|october|nov|november|dec|december)",
        cleaned.replace("_", " ").replace("-", " "),
        flags=re.IGNORECASE,
    )
    if fiscal_match:
        start_year = int(fiscal_match.group(1))
        # Fiscal year suffix (e.g., 26 from 2025-26)
        month_name = fiscal_match.group(3).lower()
        month_map = {
            "jan": 1,
            "january": 1,
            "feb": 2,
            "february": 2,
            "mar": 3,
            "march": 3,
            "apr": 4,
            "april": 4,
            "may": 5,
            "jun": 6,
            "june": 6,
            "jul": 7,
            "july": 7,
            "aug": 8,
            "august": 8,
            "sep": 9,
            "september": 9,
            "oct": 10,
            "october": 10,
            "nov": 11,
            "november": 11,
            "dec": 12,
            "december": 12,
        }
        month = month_map.get(month_name, 1)
        # Fiscal year 2025-26 means: April 2025 - March 2026
        # Jan-Mar use start_year+1; Apr-Dec use start_year
        calendar_year = start_year + 1 if month <= 3 else start_year
        parsed = dt.datetime(year=calendar_year, month=month, day=1)
        return parsed.strftime("%Y%m%dT%H%M%S")

    # Replace separators for the remaining human-readable format checks.
    cleaned = cleaned.replace("_", " ").replace("-", " ")

    formats = [
        "%d %B %Y %H:%M:%S",
        "%d %B %Y %H:%M",
        "%d %b %Y %H:%M:%S",
        "%d %b %Y %H:%M",
        "%d %B %Y",
        "%d %b %Y",
        "%B %Y",
        "%b %Y",
    ]

    for fmt in formats:
        try:
            parsed = dt.datetime.strptime(cleaned, fmt)
            return parsed.strftime("%Y%m%dT%H%M%S")
        except ValueError:
            continue

    compact_month_match = re.fullmatch(
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)(\d{2}|\d{4})",
        cleaned.replace(" ", ""),
        flags=re.IGNORECASE,
    )
    if compact_month_match:
        month_map = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "sept": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        month = month_map[compact_month_match.group(1).lower()]
        year_text = compact_month_match.group(2)
        year = 2000 + int(year_text) if len(year_text) == 2 else int(year_text)
        parsed = dt.datetime(year=year, month=month, day=1)
        return parsed.strftime("%Y%m%dT%H%M%S")

    return None


def normalize_subject_period_value(value: str) -> Optional[str]:
    """Normalize a subject period into YYYYMM for stable partitioning."""
    normalized = normalize_datetime_value(value)
    if not normalized:
        return None
    return normalized[:6]


def extract_datetime_from_pattern(pattern: str, source_value: str) -> Optional[str]:
    """Apply a regex pattern and normalize the extracted match to datetime format."""
    match = re.search(pattern, source_value, flags=re.IGNORECASE)
    if not match:
        return None

    extracted = "_".join(group for group in match.groups() if group)
    if not extracted:
        extracted = match.group(0)
    return normalize_datetime_value(extracted)


def extract_page_publication_datetime(page_text: str) -> Optional[str]:
    """Extract publication or revision datetime from page text when available."""
    if not page_text:
        return None

    candidates = [
        r"(?:published|last\s*updated)\s*:?\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)",
        r"(?:published|last\s*updated)\s*:?\s*([A-Za-z]{3,9}\s+\d{4})",
        r"(?:published|last\s*updated)\s*:?\s*(\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?)?)",
    ]

    for regex in candidates:
        match = re.search(regex, page_text, flags=re.IGNORECASE)
        if not match:
            continue
        normalized = normalize_datetime_value(match.group(1))
        if normalized:
            return normalized

    return None


def extract_datetime_from_selectors(
    page_text: str, selectors: list[str]
) -> Optional[str]:
    """Extract publication datetime from selector-like regex patterns."""
    for selector in selectors:
        extracted = extract_datetime_from_pattern(selector, page_text)
        if extracted:
            return extracted
    return None
