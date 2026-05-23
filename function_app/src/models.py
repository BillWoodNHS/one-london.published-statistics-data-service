from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PublicationDateRule:
    """Represents a rule for extracting publication date from a source."""

    source: str
    pattern: str


@dataclass
class SubjectPeriodRuleItem:
    """Represents one subject period extraction rule source+pattern pair."""

    source: str
    pattern: str


@dataclass
class SubjectPeriodRule:
    """Represents prioritized subject period extraction rules."""

    rules: List[SubjectPeriodRuleItem] = field(default_factory=list)


@dataclass
class ScrapeStep:
    """Represents a single scraping step for a dataset target."""

    link_selector: str
    text_filter: Optional[str] = None
    file_extensions: List[str] = field(default_factory=list)


@dataclass
class TargetConfig:
    """Configuration for a sub-dataset target.

    Includes scraping steps and file handling options.
    """

    sub_dataset_id: str
    scrape_steps: List[ScrapeStep]
    compression: Optional[str] = None
    excel_sheet: Optional[str] = None
    delimiter: str = ","
    encoding: str = "utf-8"
    reporting_period_columns: List[str] = field(default_factory=list)
    page_date_selectors: List[str] = field(default_factory=list)


@dataclass
class FallbackConfig:
    """Configuration for fallback/manual acquisition of datasets."""

    allow_manual_acquisition: bool = True
    manual_drop_path: str = "manual"
    max_auto_retries: int = 3
    timeout_threshold_minutes: int = 5


@dataclass
class DatasetSeriesConfig:
    """Configuration for a dataset series, including targets and fallback options."""

    dataset_id: str
    series_id: str
    entry_url: str
    publication_date: PublicationDateRule
    targets: List[TargetConfig]
    subject_period: Optional[SubjectPeriodRule] = None
    fallback: FallbackConfig = field(default_factory=FallbackConfig)


@dataclass
class DiscoveredFile:
    """Represents a discovered file, either from scraping or manual drop."""

    dataset_id: str
    series_id: str
    sub_dataset_id: str
    source_url: str
    publication_date_value: Optional[str]
    link_text: str
    subject_period_value: Optional[str] = None


@dataclass
class LoadArtifact:
    """Represents a file ready to be loaded, with all required metadata."""

    adls_path: str
    source_url: str
    series_id: str
    sub_dataset_id: str
    subject_period: str
    publication_date: str
    source_content_hash: str
    acquisition_method: str
    fallback_reason: str
