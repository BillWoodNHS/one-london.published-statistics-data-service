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
    cleaned = cleaned.replace("_", " ").replace("-", " ")

    if re.fullmatch(r"\d{8}T\d{6}", cleaned):
        return cleaned

    if re.fullmatch(r"\d{8}", cleaned):
        parsed = dt.datetime.strptime(cleaned, "%Y%m%d")
        return parsed.strftime("%Y%m%dT%H%M%S")

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
        parsed = dt.datetime.strptime(cleaned, "%Y-%m-%d")
        return parsed.strftime("%Y%m%dT%H%M%S")

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", cleaned):
        parsed = dt.datetime.strptime(cleaned, "%Y-%m-%dT%H:%M:%S")
        return parsed.strftime("%Y%m%dT%H%M%S")

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", cleaned):
        parsed = dt.datetime.strptime(cleaned, "%Y-%m-%dT%H:%M")
        return parsed.strftime("%Y%m%dT%H%M%S")

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
