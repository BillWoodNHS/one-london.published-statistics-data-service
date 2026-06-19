from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
class PeriodCoverageFileScopeHint:
    """Macro boundary hints for a file's temporal coverage."""

    duration_type: str = "unknown"
    duration_value: Optional[int] = None
    duration_unit: Optional[str] = None
    fiscal_year_start_month: Optional[int] = None


@dataclass
class PeriodCoverageHint:
    """Optional period coverage hints to prioritize runtime inference."""

    file_scope: PeriodCoverageFileScopeHint = field(
        default_factory=PeriodCoverageFileScopeHint
    )
    breakdown_granularity: List[str] = field(default_factory=list)


@dataclass
class ScrapeStep:
    """Represents a single scraping step for a dataset target."""

    link_selector: str
    text_filter: Optional[str] = None
    file_extensions: List[str] = field(default_factory=list)


@dataclass
class SiblingDiscoveryConfig:
    """Optional rules for discovering sibling pages from a seed page."""

    enabled: bool = False
    link_selector: str = "a[href]"
    url_pattern: Optional[str] = None
    text_pattern: Optional[str] = None
    max_pages: int = 25


@dataclass
class SourcePageConfig:
    """Represents one page context to scrape for a target."""

    page_url: str
    page_role: str = "default"
    partitioning_strategy: str = "none"
    scrape_steps: List[ScrapeStep] = field(default_factory=list)
    sibling_discovery: SiblingDiscoveryConfig = field(
        default_factory=SiblingDiscoveryConfig
    )


@dataclass
class SubTableConfig:
    """Configuration for a sub-table within a target.

    Files extracted from a zip are routed to this sub-table when their
    basename matches any pattern in filename_patterns.
    """

    object_name_suffix: str
    adls_path_prefix: str
    filename_patterns: List[str]


@dataclass
class TargetConfig:
    """Configuration for a sub-dataset target.

    Includes scraping steps and file handling options.
    """

    sub_dataset_id: str
    object_name_suffix: str = ""
    adls_path_prefix: str = ""
    scrape_steps: List[ScrapeStep] = field(default_factory=list)
    source_pages: List[SourcePageConfig] = field(default_factory=list)
    compression: Optional[str] = None
    excel_sheet: Optional[str] = None
    delimiter: str = ","
    encoding: str = "utf-8"
    reporting_period_columns: List[str] = field(default_factory=list)
    page_date_selectors: List[str] = field(default_factory=list)
    period_coverage: Optional[PeriodCoverageHint] = None
    sub_tables: List[SubTableConfig] = field(default_factory=list)


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
    subject_period_hint: Optional[str] = None
    page_text: str = ""
    period_coverage_hint: Optional[PeriodCoverageHint] = None
    adls_path_prefix: str = ""


@dataclass
class LoadArtifact:
    """Represents a file ready to be loaded, with all required metadata."""

    adls_path: str
    source_url: str
    series_id: str
    sub_dataset_id: str
    subject_period_from: str
    subject_period_to: str
    subject_period_coverage_type: str
    subject_period_inference_method: str
    subject_period_inference_source: str
    subject_period_inference_confidence: str
    file_scope_duration_type: str
    file_scope_duration_value: Optional[int]
    file_scope_duration_unit: str
    file_scope_fiscal_year_start_month: Optional[int]
    breakdown_granularity: List[str]
    publication_date: str
    source_content_hash: str
    acquisition_method: str
    fallback_reason: str
    downloaded_at: str = ""
    adls_path_prefix: str = ""


@dataclass
class NormalizedFile:
    """Represents a normalized file ready for loading, with all required metadata."""

    filename: str
    payload: bytes
    content_hash: str
    metrics: Dict[str, Any]
    # per-file metadata
    dataset_id: str
    sub_dataset_id: str
    series_id: str
    source_url: str
    publication_date_value: Optional[str]
    link_text: str
    subject_period_hint: Optional[str] = None
    page_text: str = ""
    period_coverage_hint: Optional[PeriodCoverageHint] = None
    adls_path_prefix: str = ""
