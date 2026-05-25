from __future__ import annotations

# ruff: noqa: E501
import argparse
import calendar
import csv
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from function_app.src.models import (  # noqa: E402
    DatasetSeriesConfig,
    PublicationDateRule,
    ScrapeStep,
    SubjectPeriodRule,
    SubjectPeriodRuleItem,
    TargetConfig,
)
from function_app.src.scraper import discover_files  # noqa: E402

DEFAULT_PAGE_DATE_SELECTORS = [
    r"(?:published|publication\s*date|last\s*updated)\s*:?\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
    r"(?:published|publication\s*date|last\s*updated)\s*:?\s*(\d{4}-\d{2}-\d{2})",
]

PUBLICATION_FALLBACK_PATTERN = (
    r"(?:published|publication\s*date|last\s*updated)\s*:?\s*"
    r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{4}-\d{2}-\d{2})"
)

MONTH_REGEX = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)"
)

PATTERN_TYPES = {
    "fiscal_year_and_month",
    "compact_month_year",
    "month_year",
}


@dataclass
class Sample:
    file_url: str
    notes: str = ""


@dataclass
class TargetHints:
    file_pattern: str = ""
    subject_period_pattern: str = ""
    fiscal_year_format: str = ""
    month_extraction: str = ""


@dataclass
class DatasetHints:
    entry_structure: str = ""
    publication_date: str = ""
    subject_period: str = ""


@dataclass
class HelperTargetInput:
    sub_dataset_id: str
    samples: List[Sample]
    include_extensions: List[str]
    preferred_link_selector: str = ""
    preferred_text_filter: str = ""
    sample_subpage_url: str = ""
    hints: Optional[TargetHints] = None


@dataclass
class HelperDatasetInput:
    dataset_id: str
    dataset_name: str
    entry_url: str
    targets: List[HelperTargetInput]
    hints: Optional[DatasetHints] = None
    source_path: str = ""


def _slugify(value: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return lowered or "unknown-dataset"


def _clean_sub_dataset_id(value: str) -> str:
    normalized = value.strip().lower() if value else ""
    if normalized in {"", "none", "n/a", "na"}:
        return "default"
    return normalized


def _is_none_like(value: str) -> bool:
    return value.strip().lower() in {"", "none", "n/a", "na"}


def _file_extension(url: str) -> str:
    path = urlparse(url).path.lower()
    if "." not in path:
        return ""
    return path.rsplit(".", maxsplit=1)[-1]


def _detect_subject_period_pattern_type(
    samples: Sequence[Sample], hints_text: str = ""
) -> str:
    if not samples:
        return "month_year"

    sample_urls = [s.file_url for s in samples if s.file_url]
    combined_text = " ".join(sample_urls) + " " + hints_text
    combined_text_lower = combined_text.lower()

    if re.search(
        r"\d{4}[-/]\d{2}[-\s_/](jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|september|oct|october|nov|november|dec|december)",
        combined_text_lower,
    ):
        return "fiscal_year_and_month"

    if re.search(
        r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|september|oct|october|nov|november|dec|december)\d{2,4}",
        combined_text_lower,
    ):
        return "compact_month_year"

    return "month_year"


def _generate_subject_period_pattern(pattern_type: str) -> str:
    if pattern_type == "fiscal_year_and_month":
        return rf"(\d{{4}}[-/]\d{{2}})[-\s_/]+{MONTH_REGEX}"
    if pattern_type == "compact_month_year":
        return rf"{MONTH_REGEX}(\d{{2,4}})"
    return rf"{MONTH_REGEX}(?:[\s_\-/]*\d{{2,4}})"


def _read_json_dataset_specs(path: Path) -> List[HelperDatasetInput]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("datasets"), list):
        records = payload["datasets"]
    elif isinstance(payload, dict):
        records = [payload]
    else:
        raise ValueError(f"JSON input must be an object: {path}")

    specs: List[HelperDatasetInput] = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"JSON record #{index} in {path} is not an object")

        schema_version = str(record.get("schema_version", "")).strip()
        if schema_version != "2.0":
            raise ValueError(
                f"Only schema_version '2.0' is supported in {path} record #{index}; got '{schema_version or 'missing'}'"
            )

        dataset_id = str(record.get("dataset_id", "")).strip()
        dataset_name = str(record.get("dataset_name", "")).strip() or dataset_id
        entry_url = str(record.get("entry_url", "")).strip()

        if not dataset_id:
            raise ValueError(f"Missing dataset_id in {path} record #{index}")
        if not entry_url:
            raise ValueError(f"Missing entry_url for dataset '{dataset_id}' in {path}")

        dataset_hints_raw = record.get("hints", {})
        dataset_hints = DatasetHints(
            entry_structure=str(dataset_hints_raw.get("entry_structure", "")).strip(),
            publication_date=str(dataset_hints_raw.get("publication_date", "")).strip(),
            subject_period=str(dataset_hints_raw.get("subject_period", "")).strip(),
        )

        target_records = record.get("targets", [])
        if not isinstance(target_records, list):
            raise ValueError(
                f"targets must be a list for dataset '{dataset_id}' in {path}"
            )

        targets: List[HelperTargetInput] = []
        for target_idx, target in enumerate(target_records, start=1):
            if not isinstance(target, dict):
                raise ValueError(
                    f"Target #{target_idx} for dataset '{dataset_id}' in {path} is not an object"
                )

            sub_dataset_id = _clean_sub_dataset_id(
                str(target.get("sub_dataset_id", "default"))
            )

            samples_raw = target.get("samples", [])
            if not isinstance(samples_raw, list):
                raise ValueError(
                    f"samples must be a list for dataset '{dataset_id}' target '{sub_dataset_id}'"
                )
            samples = [
                Sample(
                    file_url=str(s.get("file_url", "")).strip(),
                    notes=str(s.get("notes", "")).strip(),
                )
                for s in samples_raw
                if isinstance(s, dict) and str(s.get("file_url", "")).strip()
            ]
            if not samples:
                raise ValueError(
                    f"At least one samples[].file_url is required for dataset '{dataset_id}' target '{sub_dataset_id}'"
                )

            include_extensions = target.get("include_extensions", []) or []
            if not isinstance(include_extensions, list):
                raise ValueError(
                    f"include_extensions must be a list for dataset '{dataset_id}' target '{sub_dataset_id}'"
                )

            target_hints_raw = target.get("hints", {})
            target_hints = TargetHints(
                file_pattern=str(target_hints_raw.get("file_pattern", "")).strip(),
                subject_period_pattern=str(
                    target_hints_raw.get("subject_period_pattern", "")
                ).strip(),
                fiscal_year_format=str(
                    target_hints_raw.get("fiscal_year_format", "")
                ).strip(),
                month_extraction=str(
                    target_hints_raw.get("month_extraction", "")
                ).strip(),
            )

            targets.append(
                HelperTargetInput(
                    sub_dataset_id=sub_dataset_id,
                    samples=samples,
                    include_extensions=[
                        str(ext).strip().lower()
                        for ext in include_extensions
                        if str(ext).strip()
                    ],
                    preferred_link_selector=str(
                        target.get("preferred_link_selector", "")
                    ).strip(),
                    preferred_text_filter=str(
                        target.get("preferred_text_filter", "")
                    ).strip(),
                    sample_subpage_url=str(
                        target.get("sample_subpage_url", "")
                    ).strip(),
                    hints=target_hints
                    if any(
                        [
                            target_hints.file_pattern,
                            target_hints.subject_period_pattern,
                            target_hints.fiscal_year_format,
                            target_hints.month_extraction,
                        ]
                    )
                    else None,
                )
            )

        specs.append(
            HelperDatasetInput(
                dataset_id=dataset_id,
                dataset_name=dataset_name,
                entry_url=entry_url,
                targets=targets,
                hints=dataset_hints
                if any(
                    [
                        dataset_hints.entry_structure,
                        dataset_hints.publication_date,
                        dataset_hints.subject_period,
                    ]
                )
                else None,
                source_path=str(path),
            )
        )

    return specs


def _load_dataset_specs(args: argparse.Namespace) -> List[HelperDatasetInput]:
    specs: List[HelperDatasetInput] = []

    for json_path_value in args.input_json:
        json_path = Path(json_path_value)
        if not json_path.exists():
            raise FileNotFoundError(f"JSON input file not found: {json_path}")
        specs.extend(_read_json_dataset_specs(json_path))

    if args.input_json_dir:
        json_dir = Path(args.input_json_dir)
        if not json_dir.exists():
            raise FileNotFoundError(f"JSON input directory not found: {json_dir}")
        if not json_dir.is_dir():
            raise ValueError(f"JSON input path is not a directory: {json_dir}")
        for json_path in sorted(json_dir.glob("*.json")):
            specs.extend(_read_json_dataset_specs(json_path))

    if not specs:
        raise ValueError(
            "No input specs found. Provide --input-json or --input-json-dir."
        )

    deduped: Dict[str, HelperDatasetInput] = {}
    for spec in specs:
        deduped[spec.dataset_id] = spec
    return list(deduped.values())


def _write_normalized_input_specs(
    output_dir: Path, specs: Sequence[HelperDatasetInput]
) -> None:
    spec_dir = output_dir / "normalized_input_specs"
    spec_dir.mkdir(parents=True, exist_ok=True)
    for existing_path in spec_dir.glob("*.json"):
        existing_path.unlink()
    for spec in specs:
        payload = {
            "schema_version": "2.0",
            "dataset_id": spec.dataset_id,
            "dataset_name": spec.dataset_name,
            "entry_url": spec.entry_url,
            "source_path": spec.source_path,
            "hints": {
                "entry_structure": spec.hints.entry_structure if spec.hints else "",
                "publication_date": spec.hints.publication_date if spec.hints else "",
                "subject_period": spec.hints.subject_period if spec.hints else "",
            },
            "targets": [
                {
                    "sub_dataset_id": target.sub_dataset_id,
                    "sample_subpage_url": target.sample_subpage_url,
                    "samples": [
                        {"file_url": sample.file_url, "notes": sample.notes}
                        for sample in target.samples
                    ],
                    "notes": " | ".join([s.notes for s in target.samples if s.notes]),
                    "include_extensions": target.include_extensions,
                    "preferred_link_selector": target.preferred_link_selector,
                    "preferred_text_filter": target.preferred_text_filter,
                    "hints": {
                        "file_pattern": target.hints.file_pattern
                        if target.hints
                        else "",
                        "subject_period_pattern": target.hints.subject_period_pattern
                        if target.hints
                        else "",
                        "fiscal_year_format": target.hints.fiscal_year_format
                        if target.hints
                        else "",
                        "month_extraction": target.hints.month_extraction
                        if target.hints
                        else "",
                    },
                }
                for target in spec.targets
            ],
        }
        path = spec_dir / f"{spec.dataset_id}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _fetch_page(session: requests.Session, url: str) -> Optional[BeautifulSoup]:
    try:
        response = session.get(url, timeout=60)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except Exception:
        return None


def _all_links(soup: BeautifulSoup) -> List[Tuple[str, str]]:
    links: List[Tuple[str, str]] = []
    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        text = " ".join(anchor.get_text(separator=" ", strip=True).split())
        links.append((href, text))
    return links


def _looks_like_formatted_report(note: str) -> bool:
    lowered = note.lower()
    return "formatted report" in lowered or "multiple tabs" in lowered


def _contains_date_text(text: str) -> bool:
    date_patterns = [
        r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b",
        r"\b[A-Za-z]{3,9}\s+\d{4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    ]
    return any(
        re.search(pattern, text, flags=re.IGNORECASE) for pattern in date_patterns
    )


def _best_link_text_hint(
    example_file_url: str, links: Iterable[Tuple[str, str]]
) -> Optional[str]:
    target_tail = urlparse(example_file_url).path.rsplit("/", maxsplit=1)[-1].lower()
    if not target_tail:
        return None

    exact = [
        text for href, text in links if href.lower().endswith(target_tail) and text
    ]
    if exact:
        return exact[0]

    partial = [
        text
        for href, text in links
        if target_tail in href.lower() or href.lower().endswith(target_tail[:24])
    ]
    if partial:
        return partial[0]

    return None


def _escape_for_regex(text: str) -> str:
    escaped = re.escape(text.strip())
    escaped = escaped.replace(r"\ ", r"\\s+")
    return escaped


def _generalize_link_text(text: str) -> str:
    value = text.strip()
    if not value:
        return value

    value = re.sub(r"\([^)]*\)", " ", value)
    month_names = (
        "january|february|march|april|may|june|july|august|"
        "september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
    )
    value = re.sub(
        rf"\b(?:{month_names})\b\s*[-/]?\s*\d{{2,4}}\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\b\d{4}\b", " ", value)
    value = " ".join(value.split())
    return value


MONTH_NAME_TO_NUMBER = {
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


def _year_to_int(value: str) -> int:
    year = int(value)
    if year < 100:
        return 2000 + year
    return year


def _month_tokens(text: str) -> List[Tuple[int, int]]:
    pattern = (
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
        r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"[\s_\-/]*(\d{2,4})\b"
    )
    tokens: List[Tuple[int, int]] = []
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        month_name = match.group(1).lower()
        year_text = match.group(2)
        month = MONTH_NAME_TO_NUMBER.get(month_name)
        if not month:
            continue
        year = _year_to_int(year_text)
        tokens.append((year, month))
    return tokens


def _month_start_end(year: int, month: int) -> Tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    from_value = f"{year:04d}{month:02d}01T000000"
    to_value = f"{year:04d}{month:02d}{last_day:02d}T235959"
    return from_value, to_value


def _infer_subject_period(link_text: str, source_url: str) -> Tuple[str, str, str]:
    text_tokens = _month_tokens(link_text)
    if len(text_tokens) >= 2:
        ordered = sorted(text_tokens)
        from_value, _ = _month_start_end(*ordered[0])
        _, to_value = _month_start_end(*ordered[-1])
        return from_value, to_value, "range_from_link_text"
    if len(text_tokens) == 1:
        from_value, to_value = _month_start_end(*text_tokens[0])
        return from_value, to_value, "single_month_from_link_text"

    url_tokens = _month_tokens(source_url)
    if len(url_tokens) >= 2:
        ordered = sorted(url_tokens)
        from_value, _ = _month_start_end(*ordered[0])
        _, to_value = _month_start_end(*ordered[-1])
        return from_value, to_value, "range_from_url"
    if len(url_tokens) == 1:
        from_value, to_value = _month_start_end(*url_tokens[0])
        return from_value, to_value, "single_month_from_url"

    return "", "", "not_inferred"


def _choose_file_pattern(
    example_file_url: str, links: Sequence[Tuple[str, str]]
) -> Optional[str]:
    hint = _best_link_text_hint(example_file_url, links)
    if not hint:
        return None

    generalized = _generalize_link_text(hint)
    if not generalized:
        return None

    words = [word for word in re.split(r"\s+", generalized) if len(word) >= 3]
    if len(words) < 2:
        return None

    return _escape_for_regex(" ".join(words[:6]))


def _stable_sub_link_token(sub_links: Sequence[str]) -> Optional[str]:
    normalized_sub_paths = [
        urlparse(link).path.rstrip("/").lower()
        for link in sub_links
        if not _is_none_like(link)
    ]
    if not normalized_sub_paths:
        return None

    sample_path = normalized_sub_paths[0]
    leaf = sample_path.rsplit("/", maxsplit=1)[-1]
    if not leaf:
        return None

    token = re.sub(r"\b\d{2,4}\b", "", leaf)
    token = re.sub(r"-{2,}", "-", token).strip("-")
    return token or None


def _resolve_subject_period_pattern_type(dataset: HelperDatasetInput) -> str:
    explicit_types: List[str] = []
    for target in dataset.targets:
        if target.hints and target.hints.subject_period_pattern:
            hinted = target.hints.subject_period_pattern.strip().lower()
            if hinted in PATTERN_TYPES:
                explicit_types.append(hinted)
    if explicit_types:
        return explicit_types[0]

    samples: List[Sample] = []
    hints_parts: List[str] = []
    if dataset.hints:
        hints_parts.append(dataset.hints.subject_period)
    for target in dataset.targets:
        samples.extend(target.samples)
        hints_parts.extend([sample.notes for sample in target.samples if sample.notes])
        if target.hints:
            hints_parts.extend(
                [
                    target.hints.subject_period_pattern,
                    target.hints.fiscal_year_format,
                    target.hints.month_extraction,
                ]
            )

    return _detect_subject_period_pattern_type(samples, " ".join(hints_parts))


def _build_config_for_dataset(
    dataset: HelperDatasetInput,
    session: requests.Session,
) -> Tuple[Dict[str, object], List[Dict[str, str]]]:
    if not dataset.entry_url:
        raise ValueError(f"Dataset '{dataset.dataset_id}' has no usable entry URL")

    suggestion_rows: List[Dict[str, str]] = []
    targets: List[Dict[str, object]] = []

    subject_period_pattern_type = _resolve_subject_period_pattern_type(dataset)
    subject_period_pattern = _generate_subject_period_pattern(
        subject_period_pattern_type
    )

    for target_input in sorted(
        dataset.targets, key=lambda target: target.sub_dataset_id
    ):
        target_notes = " | ".join(
            [sample.notes for sample in target_input.samples if sample.notes]
        )
        normalized_sub_dataset_id = _clean_sub_dataset_id(target_input.sub_dataset_id)
        if (
            _looks_like_formatted_report(target_notes)
            or normalized_sub_dataset_id == "summary"
        ):
            continue

        example_file = target_input.samples[0].file_url if target_input.samples else ""
        sub_links = (
            [target_input.sample_subpage_url]
            if target_input.sample_subpage_url
            and not _is_none_like(target_input.sample_subpage_url)
            else []
        )
        page_for_file = sub_links[0] if sub_links else dataset.entry_url
        sub_soup = _fetch_page(session, page_for_file)
        sub_page_links = _all_links(sub_soup) if sub_soup else []

        extensions = sorted(
            {
                ext.lower()
                for ext in target_input.include_extensions
                if ext and ext.strip()
            }
        )
        if not extensions and not _is_none_like(example_file):
            file_extension = _file_extension(example_file)
            if file_extension:
                extensions = [file_extension]

        file_filter = target_input.preferred_text_filter or (
            _choose_file_pattern(example_file, sub_page_links) if example_file else None
        )

        sub_link_token = _stable_sub_link_token(sub_links)

        scrape_steps: List[Dict[str, object]] = []
        if sub_links:
            step1_selector = target_input.preferred_link_selector or (
                f'a[href*="{sub_link_token}"]' if sub_link_token else "a[href]"
            )
            step1: Dict[str, object] = {"link_selector": step1_selector}
            scrape_steps.append(step1)

        step_last_selector = target_input.preferred_link_selector or "a[href]"
        step_last: Dict[str, object] = {"link_selector": step_last_selector}
        if file_filter:
            step_last["text_filter"] = file_filter
        if extensions:
            step_last["file_extensions"] = extensions
        scrape_steps.append(step_last)

        targets.append(
            {
                "sub_dataset_id": _slugify(normalized_sub_dataset_id),
                "scrape_steps": scrape_steps,
                "reporting_period_columns": [],
                "page_date_selectors": DEFAULT_PAGE_DATE_SELECTORS,
            }
        )

        suggestion_rows.append(
            {
                "dataset_name": dataset.dataset_name,
                "dataset_id": dataset.dataset_id,
                "sub_collection": normalized_sub_dataset_id,
                "entry_url": dataset.entry_url,
                "example_sub_link": sub_links[0] if sub_links else "",
                "example_target_file": example_file,
                "suggested_sub_link_text_filter": "",
                "suggested_sub_link_selector": f'a[href*="{sub_link_token}"]'
                if sub_link_token
                else "a[href]",
                "suggested_file_text_filter": file_filter or "",
                "suggested_extensions": "|".join(extensions),
                "page_for_file_matching": page_for_file,
                "source_path": dataset.source_path,
                "page_contains_date_hint": "yes"
                if sub_soup and _contains_date_text(sub_soup.get_text(" ", strip=True))
                else "no",
                "subject_period_pattern_type": subject_period_pattern_type,
                "skip_reason": "",
            }
        )

    config = {
        "dataset_id": dataset.dataset_id,
        "series_id": dataset.dataset_id,
        "entry_url": dataset.entry_url,
        "publication_date": {
            "source": "link_text",
            "pattern": PUBLICATION_FALLBACK_PATTERN,
        },
        "subject_period": {
            "rules": [
                {
                    "source": "file_name",
                    "pattern": subject_period_pattern,
                },
                {
                    "source": "url_segment",
                    "pattern": subject_period_pattern,
                },
                {
                    "source": "page_text",
                    "pattern": subject_period_pattern,
                },
            ]
        },
        "fallback": {
            "allow_manual_acquisition": True,
            "manual_drop_path": f"manual/{dataset.dataset_id}",
            "max_auto_retries": 3,
            "timeout_threshold_minutes": 5,
        },
        "targets": targets,
    }

    return config, suggestion_rows


def _validate_config_matches(config: Dict[str, object]) -> List[Dict[str, str]]:
    series_config = DatasetSeriesConfig(
        dataset_id=str(config["dataset_id"]),
        series_id=str(config["series_id"]),
        entry_url=str(config["entry_url"]),
        publication_date=PublicationDateRule(**config["publication_date"]),
        subject_period=(
            SubjectPeriodRule(
                rules=[
                    SubjectPeriodRuleItem(**rule)
                    for rule in config.get("subject_period", {}).get("rules", [])
                ]
            )
            if config.get("subject_period")
            else None
        ),
        targets=[
            TargetConfig(
                sub_dataset_id=str(target["sub_dataset_id"]),
                scrape_steps=[ScrapeStep(**step) for step in target["scrape_steps"]],
                reporting_period_columns=target.get("reporting_period_columns", []),
                page_date_selectors=target.get("page_date_selectors", []),
            )
            for target in config["targets"]
        ],
    )

    rows: List[Dict[str, str]] = []
    try:
        discovered = discover_files(series_config)
    except Exception as exc:
        for target in series_config.targets:
            rows.append(
                {
                    "dataset_id": series_config.dataset_id,
                    "sub_dataset_id": target.sub_dataset_id,
                    "status": "error",
                    "source_url": "",
                    "link_text": "",
                    "publication_date_value": "",
                    "subject_period_from_value": "",
                    "subject_period_to_value": "",
                    "subject_period_inference_method": "not_inferred",
                    "message": str(exc),
                }
            )
        return rows

    if not discovered:
        for target in series_config.targets:
            rows.append(
                {
                    "dataset_id": series_config.dataset_id,
                    "sub_dataset_id": target.sub_dataset_id,
                    "status": "no_matches",
                    "source_url": "",
                    "link_text": "",
                    "publication_date_value": "",
                    "subject_period_from_value": "",
                    "subject_period_to_value": "",
                    "subject_period_inference_method": "not_inferred",
                    "message": "No links matched generated scrape steps",
                }
            )
        return rows

    for file in discovered:
        subject_from, subject_to, subject_method = _infer_subject_period(
            file.link_text or "", file.source_url or ""
        )
        rows.append(
            {
                "dataset_id": file.dataset_id,
                "sub_dataset_id": file.sub_dataset_id,
                "status": "match",
                "source_url": file.source_url,
                "link_text": file.link_text,
                "publication_date_value": file.publication_date_value or "",
                "subject_period_from_value": subject_from,
                "subject_period_to_value": subject_to,
                "subject_period_inference_method": subject_method,
                "message": "",
            }
        )
    return rows


def _write_csv(path: Path, rows: Sequence[Dict[str, str]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _build_for_datasets(
    specs: Sequence[HelperDatasetInput],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_dir = output_dir / "generated_configs"
    generated_dir.mkdir(parents=True, exist_ok=True)
    for existing_path in generated_dir.iterdir():
        if existing_path.is_file():
            existing_path.unlink()
        elif existing_path.is_dir():
            shutil.rmtree(existing_path)
    _write_normalized_input_specs(output_dir, specs)

    session = requests.Session()
    all_suggestions: List[Dict[str, str]] = []
    all_matches: List[Dict[str, str]] = []

    for spec in specs:
        config, suggestions = _build_config_for_dataset(spec, session)
        yaml_path = generated_dir / f"{spec.dataset_id}.yaml"
        yaml_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

        matches = _validate_config_matches(config)
        for row in matches:
            row["yaml_path"] = str(yaml_path)

        all_suggestions.extend(suggestions)
        all_matches.extend(matches)

    _write_csv(output_dir / "helper_suggestions.csv", all_suggestions)
    _write_csv(output_dir / "matches_found.csv", all_matches)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build scraper YAML configs from v2 JSON helper specs "
            "and run non-download discovery validation."
        )
    )
    parser.add_argument(
        "--input-json",
        action="append",
        default=[],
        help=(
            "Path to v2 JSON dataset spec. Repeat for multiple files. "
            'Supports a single dataset object or {"datasets": [...]}.'
        ),
    )
    parser.add_argument(
        "--input-json-dir",
        default="",
        help="Directory of v2 JSON dataset specs (*.json).",
    )
    parser.add_argument(
        "--dataset",
        action="append",
        default=[],
        help=(
            "Dataset ID or dataset name to process. Repeat to process multiple datasets. "
            "If omitted, process all loaded specs."
        ),
    )
    parser.add_argument(
        "--max-datasets",
        type=int,
        default=0,
        help="Optional cap on number of datasets to process (0 means no cap).",
    )
    parser.add_argument(
        "--output-dir",
        default="logs/local_helper",
        help="Directory for generated YAML and CSV outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    specs = _load_dataset_specs(args)

    indexed_specs: Dict[str, HelperDatasetInput] = {}
    for spec in specs:
        indexed_specs[spec.dataset_id] = spec
        indexed_specs[spec.dataset_name] = spec

    if args.dataset:
        selected_specs: List[HelperDatasetInput] = []
        seen: set[str] = set()
        for selector in args.dataset:
            spec = indexed_specs.get(selector)
            if not spec:
                continue
            if spec.dataset_id in seen:
                continue
            selected_specs.append(spec)
            seen.add(spec.dataset_id)
    else:
        selected_specs = sorted(specs, key=lambda spec: spec.dataset_id)

    if not selected_specs:
        raise ValueError("No matching datasets selected")

    if args.max_datasets > 0:
        selected_specs = selected_specs[: args.max_datasets]

    output_dir = Path(args.output_dir)
    _build_for_datasets(selected_specs, output_dir)

    print(f"Processed datasets: {len(selected_specs)}")
    print(f"Output directory: {output_dir.resolve()}")
    print(f"Generated YAML dir: {(output_dir / 'generated_configs').resolve()}")
    print(
        f"Normalized input specs dir: {(output_dir / 'normalized_input_specs').resolve()}"
    )
    print(f"Suggestions CSV: {(output_dir / 'helper_suggestions.csv').resolve()}")
    print(f"Matches CSV: {(output_dir / 'matches_found.csv').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
