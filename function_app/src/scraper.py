from __future__ import annotations

import re
from typing import List, Sequence, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .datetime_utils import (
    extract_datetime_from_pattern,
    extract_datetime_from_selectors,
    extract_page_publication_datetime,
    normalize_subject_period_value,
)
from .models import DatasetSeriesConfig, DiscoveredFile, ScrapeStep, TargetConfig


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
) -> List[Tuple[str, str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    page_text = " ".join(soup.get_text(separator=" ", strip=True).split())
    page_publication_datetime = extract_datetime_from_selectors(
        page_text, list(page_date_selectors or [])
    ) or extract_page_publication_datetime(page_text)
    links = []

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

        links.append((full_url, text, page_publication_datetime))

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


def _discover_for_target(
    config: DatasetSeriesConfig,
    target: TargetConfig,
    session: requests.Session,
) -> List[DiscoveredFile]:
    candidates: List[Tuple[str, str, str | None]] = [(config.entry_url, "", None)]

    for step in target.scrape_steps:
        next_candidates: List[Tuple[str, str, str | None]] = []
        for page_url, _, _ in candidates:
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
    for file_url, link_text, page_publication_datetime in candidates:
        source_for_publication = _publication_source_value(
            config.publication_date.source, link_text, file_url
        )
        publication_date_value = page_publication_datetime or _publication_date_from(
            config.publication_date.pattern, source_for_publication
        )

        subject_period_value = None
        if config.subject_period:
            source_for_subject_period = _publication_source_value(
                config.subject_period.source, link_text, file_url
            )
            extracted = _publication_date_from(
                config.subject_period.pattern, source_for_subject_period
            )
            if extracted:
                subject_period_value = normalize_subject_period_value(extracted)

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


def discover_files(config: DatasetSeriesConfig) -> List[DiscoveredFile]:
    session = requests.Session()
    all_files: List[DiscoveredFile] = []

    for target in config.targets:
        all_files.extend(_discover_for_target(config, target, session))

    return all_files
