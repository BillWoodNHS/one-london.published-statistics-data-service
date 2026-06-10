from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple

from .datetime_utils import normalize_datetime_value


@dataclass
class PeriodCoverage:
    subject_period_from: str
    subject_period_to: str
    coverage_type: str
    inference_method: str
    inference_source: str
    confidence: str


_MONTH_NAME_TO_NUMBER = {
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
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def _unknown() -> PeriodCoverage:
    return PeriodCoverage(
        subject_period_from="",
        subject_period_to="",
        coverage_type="unknown",
        inference_method="not_inferred",
        inference_source="none",
        confidence="low",
    )


def _month_start_end(year: int, month: int) -> Tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    from_value = f"{year:04d}{month:02d}01T000000"
    to_value = f"{year:04d}{month:02d}{last_day:02d}T235959"
    return from_value, to_value


def _year_to_int(value: str) -> int:
    year = int(value)
    if year < 100:
        return 2000 + year
    return year


def _month_tokens(text: str) -> list[Tuple[int, int]]:
    pattern = (
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
        r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"[\s_\-/]*(\d{2,4})\b"
    )
    tokens: list[Tuple[int, int]] = []
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        month_name = match.group(1).lower()
        year_text = match.group(2)
        month = _MONTH_NAME_TO_NUMBER.get(month_name)
        if not month:
            continue
        tokens.append((_year_to_int(year_text), month))
    return tokens


def _from_yyyymm(subject_period_hint: str) -> Optional[PeriodCoverage]:
    cleaned = (subject_period_hint or "").strip()
    if not re.fullmatch(r"\d{6}", cleaned):
        return None
    year = int(cleaned[:4])
    month = int(cleaned[4:6])
    if month < 1 or month > 12:
        return None
    from_value, to_value = _month_start_end(year, month)
    return PeriodCoverage(
        subject_period_from=from_value,
        subject_period_to=to_value,
        coverage_type="single_month",
        inference_method="subject_period_rule_yyyymm",
        inference_source="subject_period_hint",
        confidence="high",
    )


def _single_or_range_from_month_tokens(
    text: str,
    source: str,
) -> Optional[PeriodCoverage]:
    tokens = _month_tokens(text)
    if not tokens:
        return None

    ordered = sorted(tokens)
    first = ordered[0]
    last = ordered[-1]
    from_value, _ = _month_start_end(*first)
    _, to_value = _month_start_end(*last)

    coverage_type = "single_month" if first == last else "month_range"
    method = (
        "single_month_from_" + source
        if coverage_type == "single_month"
        else "range_from_" + source
    )
    return PeriodCoverage(
        subject_period_from=from_value,
        subject_period_to=to_value,
        coverage_type=coverage_type,
        inference_method=method,
        inference_source=source,
        confidence="high" if coverage_type == "single_month" else "medium",
    )


def _infer_ytd_coverage(
    text: str,
    source: str,
    fiscal_year_start_month: int = 4,
) -> Optional[PeriodCoverage]:
    lowered = text.lower()
    month_tokens = _month_tokens(text)
    if not month_tokens:
        return None

    _, to_value = _month_start_end(*sorted(month_tokens)[-1])
    year = int(to_value[:4])
    month = int(to_value[4:6])

    if "fiscal" in lowered or "fytd" in lowered:
        start_year = year if month >= fiscal_year_start_month else year - 1
        from_value = f"{start_year:04d}{fiscal_year_start_month:02d}01T000000"
        return PeriodCoverage(
            subject_period_from=from_value,
            subject_period_to=to_value,
            coverage_type="fiscal_ytd",
            inference_method="fiscal_ytd_from_" + source,
            inference_source=source,
            confidence="medium",
        )

    if "year to date" in lowered or "ytd" in lowered:
        from_value = f"{year:04d}0101T000000"
        return PeriodCoverage(
            subject_period_from=from_value,
            subject_period_to=to_value,
            coverage_type="calendar_ytd",
            inference_method="calendar_ytd_from_" + source,
            inference_source=source,
            confidence="medium",
        )

    return None


def _infer_rolling_12_coverage(text: str, source: str) -> Optional[PeriodCoverage]:
    lowered = text.lower()
    if "rolling 12" not in lowered and "12 month rolling" not in lowered:
        return None

    month_tokens = _month_tokens(text)
    if not month_tokens:
        return None

    year, month = sorted(month_tokens)[-1]
    to_month_start = dt.date(year, month, 1)
    start_month_index = to_month_start.month - 11
    start_year = to_month_start.year
    while start_month_index <= 0:
        start_month_index += 12
        start_year -= 1

    from_value = f"{start_year:04d}{start_month_index:02d}01T000000"
    _, to_value = _month_start_end(year, month)
    return PeriodCoverage(
        subject_period_from=from_value,
        subject_period_to=to_value,
        coverage_type="rolling_12_month",
        inference_method="rolling_12_from_" + source,
        inference_source=source,
        confidence="medium",
    )


def _infer_daily_coverage(text: str, source: str) -> Optional[PeriodCoverage]:
    normalized = normalize_datetime_value(text)
    if not normalized:
        return None

    day = normalized[:8]
    from_value = day + "T000000"
    to_value = day + "T235959"
    return PeriodCoverage(
        subject_period_from=from_value,
        subject_period_to=to_value,
        coverage_type="daily",
        inference_method="daily_from_" + source,
        inference_source=source,
        confidence="low",
    )


def infer_period_coverage(
    subject_period_hint: Optional[str],
    link_text: str,
    source_url: str,
    page_text: str = "",
    duration_type_hint: str = "unknown",
    duration_value_hint: Optional[int] = None,
    duration_unit_hint: Optional[str] = None,
    fiscal_year_start_month_hint: Optional[int] = None,
) -> PeriodCoverage:
    hint_coverage = _from_yyyymm(subject_period_hint or "")
    if hint_coverage:
        return hint_coverage

    evidence: Iterable[Tuple[str, str]] = (
        (link_text or "", "link_text"),
        (Path(source_url or "").name, "file_name"),
        (source_url or "", "source_url"),
        (page_text or "", "page_text"),
    )

    evidence_map = {source: text for text, source in evidence}
    ordered_sources = [
        source
        for source in ["file_name", "link_text", "source_url", "page_text"]
        if source in evidence_map
    ]
    for source in ["link_text", "file_name", "source_url", "page_text"]:
        if source not in ordered_sources:
            ordered_sources.append(source)

    fiscal_year_start_month = fiscal_year_start_month_hint or 4

    if (
        duration_type_hint == "rolling"
        and duration_value_hint == 12
        and duration_unit_hint == "month"
    ):
        for source in ordered_sources:
            rolling = _infer_rolling_12_coverage(evidence_map.get(source, ""), source)
            if rolling:
                return rolling

    if duration_type_hint in {"calendar_ytd", "fiscal_ytd"}:
        for source in ordered_sources:
            ytd = _infer_ytd_coverage(
                evidence_map.get(source, ""),
                source,
                fiscal_year_start_month=fiscal_year_start_month,
            )
            if ytd:
                if (
                    duration_type_hint == "fiscal_ytd"
                    and ytd.coverage_type == "calendar_ytd"
                ):
                    continue
                return ytd

    for source in ordered_sources:
        text = evidence_map.get(source, "")
        if not text:
            continue
        rolling = _infer_rolling_12_coverage(text, source)
        if rolling:
            return rolling

        ytd = _infer_ytd_coverage(
            text, source, fiscal_year_start_month=fiscal_year_start_month
        )
        if ytd:
            return ytd

        month_based = _single_or_range_from_month_tokens(text, source)
        if month_based:
            return month_based

        daily = _infer_daily_coverage(text, source)
        if daily:
            return daily

    return _unknown()
