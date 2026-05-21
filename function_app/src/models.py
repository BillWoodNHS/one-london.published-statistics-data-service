from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PublicationDateRule:
    source: str
    pattern: str


@dataclass
class ScrapeStep:
    link_selector: str
    text_filter: Optional[str] = None
    file_extensions: List[str] = field(default_factory=list)


@dataclass
class TargetConfig:
    sub_dataset_id: str
    scrape_steps: List[ScrapeStep]
    compression: Optional[str] = None
    excel_sheet: Optional[str] = None
    delimiter: str = ","
    encoding: str = "utf-8"
    reporting_period_columns: List[str] = field(default_factory=list)


@dataclass
class FallbackConfig:
    allow_manual_acquisition: bool = True
    manual_drop_path: str = "manual"
    max_auto_retries: int = 3
    timeout_threshold_minutes: int = 5


@dataclass
class DatasetSeriesConfig:
    dataset_id: str
    series_id: str
    entry_url: str
    publication_date: PublicationDateRule
    targets: List[TargetConfig]
    fallback: FallbackConfig = field(default_factory=FallbackConfig)


@dataclass
class DiscoveredFile:
    dataset_id: str
    series_id: str
    sub_dataset_id: str
    source_url: str
    publication_date_value: str
    link_text: str


@dataclass
class LoadArtifact:
    adls_path: str
    source_url: str
    series_id: str
    sub_dataset_id: str
    publication_date: str
    source_content_hash: str
    acquisition_method: str
    fallback_reason: str
