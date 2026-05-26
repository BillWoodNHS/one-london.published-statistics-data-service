from __future__ import annotations

import re
from pathlib import Path
from typing import List, Sequence, Set, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .datetime_utils import (
    extract_datetime_from_pattern,
    extract_datetime_from_selectors,
    extract_page_publication_datetime,
    normalize_subject_period_value,
)
from .models import (
    DatasetSeriesConfig,
    DiscoveredFile,
    ScrapeStep,
    SourcePageConfig,
    SubjectPeriodRuleItem,
    TargetConfig,
)


class ScraperError(Exception):
    pass


def _matches_extensions(url: str, extensions: Sequence[str]) -> bool:
    if not extensions:
        return True

    lowered = url.lower()
    return any(lowered.endswith(f".{ext.lower()}") for ext in extensions)


def _extract_links(
    page_url: str,
    html: str,
    step: ScrapeStep,
    page_date_selectors: Sequence[str] | None = None,
) -> List[Tuple[str, str, str | None, str]]:
    soup = BeautifulSoup(html, "html.parser")
    page_text = " ".join(soup.get_text(separator=" ", strip=True).split())
    page_publication_datetime = extract_datetime_from_selectors(
        page_text, list(page_date_selectors or [])
    ) or extract_page_publication_datetime(page_text)
    links: List[Tuple[str, str, str | None, str]] = []

    pattern = (
        re.compile(step.text_filter, flags=re.IGNORECASE) if step.text_filter else None
    )

    for node in soup.select(step.link_selector):
        href = node.get("href")
        if not href:
            continue

        full_url = urljoin(page_url, href)
        text = " ".join(node.get_text(separator=" ", strip=True).split())

        if pattern and not pattern.search(text):
            continue

        if not _matches_extensions(full_url, step.file_extensions):
            continue

        links.append((full_url, text, page_publication_datetime, page_text))

    return links


def _publication_date_from(rule_pattern: str, source_value: str) -> str | None:
    return extract_datetime_from_pattern(rule_pattern, source_value)


def _publication_source_value(source_type: str, link_text: str, file_url: str) -> str:
    if source_type == "link_text":
        return link_text
    if source_type == "url_segment":
        return file_url
    if source_type == "manual":
        return link_text or file_url
    return link_text or file_url


def _subject_period_source_value(
    source_type: str, link_text: str, file_url: str, page_text: str
) -> str:
    if source_type in {"file_name", "filename"}:
        return Path(file_url).name
    if source_type == "url_segment":
        return file_url
    if source_type in {"page_text", "page_elements"}:
        return page_text
    if source_type == "link_text":
        return link_text
    return link_text or file_url


def _extract_subject_period_from_rules(
    rules: Sequence[SubjectPeriodRuleItem],
    link_text: str,
    file_url: str,
    page_text: str,
) -> str | None:
    for rule in rules:
        source_value = _subject_period_source_value(
            rule.source, link_text, file_url, page_text
        )
        extracted = _publication_date_from(rule.pattern, source_value)
        if extracted:
            normalized = normalize_subject_period_value(extracted)
            if normalized:
                return normalized
    return None


def _canonical_url(url: str) -> str:
    return url.strip().rstrip("/")


def _looks_like_subject_period_page_ref(value: str) -> bool:
    lowered = value.lower()
    patterns = [
        r"\b(?:19|20)\d{2}\b",
        r"\bfy[-_\s]?\d{4}(?:[-_/]\d{2,4})?\b",
        r"\bq[1-4]\b",
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)(?:uary|ruary|ch|il|e|y|ust|tember|ober|ember)?\b",
    ]
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in patterns)


def _discover_sibling_pages(
    seed_page_url: str,
    page_html: str,
    source_page: SourcePageConfig,
) -> List[str]:
    config = source_page.sibling_discovery
    if not config.enabled:
        return [seed_page_url]

    soup = BeautifulSoup(page_html, "html.parser")
    url_pattern = (
        re.compile(config.url_pattern, flags=re.IGNORECASE)
        if config.url_pattern
        else None
    )
    text_pattern = (
        re.compile(config.text_pattern, flags=re.IGNORECASE)
        if config.text_pattern
        else None
    )

    discovered: List[str] = [seed_page_url]
    seen: Set[str] = {_canonical_url(seed_page_url)}
    max_pages = max(1, config.max_pages)

    for node in soup.select(config.link_selector or "a[href]"):
        href = node.get("href")
        if not href:
            continue

        full_url = _canonical_url(urljoin(seed_page_url, href))
        text = " ".join(node.get_text(separator=" ", strip=True).split())
        href_lower = full_url.lower()

        # Skip direct file links; sibling discovery is for page URLs.
        if re.search(
            r"\.(csv|xlsx?|zip|xlsm|txt|json|xml|pdf|docx?|pptx?)(?:$|\?)", href_lower
        ):
            continue

        if full_url in seen:
            continue

        if url_pattern and not url_pattern.search(full_url):
            continue
        if text_pattern and not text_pattern.search(text):
            continue
        if not url_pattern and not text_pattern:
            if not (
                _looks_like_subject_period_page_ref(full_url)
                or _looks_like_subject_period_page_ref(text)
            ):
                continue

        seen.add(full_url)
        discovered.append(full_url)
        if len(discovered) >= max_pages:
            break

    return discovered


def _discover_from_page(
    config: DatasetSeriesConfig,
    target: TargetConfig,
    source_page: SourcePageConfig,
    session: requests.Session,
) -> List[DiscoveredFile]:
    seed_response = session.get(source_page.page_url, timeout=60)
    seed_response.raise_for_status()

    page_urls = _discover_sibling_pages(
        seed_page_url=source_page.page_url,
        page_html=seed_response.text,
        source_page=source_page,
    )

    candidates: List[Tuple[str, str, str | None, str]] = [
        (url, "", None, "") for url in page_urls
    ]

    for step in source_page.scrape_steps:
        next_candidates: List[Tuple[str, str, str | None, str]] = []
        for page_url, _, _, _ in candidates:
            response = session.get(page_url, timeout=60)
            response.raise_for_status()
            next_candidates.extend(
                _extract_links(
                    page_url,
                    response.text,
                    step,
                    page_date_selectors=target.page_date_selectors,
                )
            )
        candidates = next_candidates

    discovered: List[DiscoveredFile] = []
    for file_url, link_text, page_publication_datetime, page_text in candidates:
        source_for_publication = _publication_source_value(
            config.publication_date.source, link_text, file_url
        )
        publication_date_value = page_publication_datetime or _publication_date_from(
            config.publication_date.pattern, source_for_publication
        )

        subject_period_value = None
        if config.subject_period:
            subject_period_value = _extract_subject_period_from_rules(
                config.subject_period.rules,
                link_text,
                file_url,
                page_text,
            )

        discovered.append(
            DiscoveredFile(
                dataset_id=config.dataset_id,
                series_id=config.series_id,
                sub_dataset_id=target.sub_dataset_id,
                source_url=file_url,
                publication_date_value=publication_date_value,
                link_text=link_text,
                subject_period_value=subject_period_value,
            )
        )

    return discovered


def _discover_for_target(
    config: DatasetSeriesConfig,
    target: TargetConfig,
    session: requests.Session,
) -> List[DiscoveredFile]:
    source_pages = target.source_pages or [
        SourcePageConfig(
            page_url=config.entry_url,
            page_role="default",
            partitioning_strategy="none",
            scrape_steps=target.scrape_steps,
        )
    ]

    discovered: List[DiscoveredFile] = []
    for source_page in source_pages:
        discovered.extend(_discover_from_page(config, target, source_page, session))
    return discovered


def discover_files(config: DatasetSeriesConfig) -> List[DiscoveredFile]:
    session = requests.Session()
    all_files: List[DiscoveredFile] = []

    for target in config.targets:
        all_files.extend(_discover_for_target(config, target, session))

    # Deduplicate by (sub_dataset_id, source_url) to avoid duplicate files when
    # current and archive page traversals overlap.
    deduped: List[DiscoveredFile] = []
    seen: Set[Tuple[str, str]] = set()
    for item in all_files:
        key = (item.sub_dataset_id, _canonical_url(item.source_url))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped
