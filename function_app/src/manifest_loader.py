from __future__ import annotations

import re
from pathlib import Path
from typing import List

import yaml

from .models import (
    DatasetSeriesConfig,
    FallbackConfig,
    PeriodCoverageHint,
    PeriodCoverageFileScopeHint,
    PublicationDateRule,
    ScrapeStep,
    SiblingDiscoveryConfig,
    SourcePageConfig,
    SubjectPeriodRule,
    SubjectPeriodRuleItem,
    TargetConfig,
)


class ManifestError(Exception):
    """Custom exception for manifest loading errors."""

    pass


OBJECT_NAME_SUFFIX_PATTERN = re.compile(r"^[A-Z0-9_]+$")
RESERVED_OBJECT_NAME_PREFIXES = ("STG_", "PIPE_", "INGEST_", "RAW_")
ADLS_PATH_PREFIX_PATTERN = re.compile(
    r"^[a-z0-9_\-][a-z0-9_\-/]*[a-z0-9_\-]$|^[a-z0-9_\-]$"
)


def _require(value, key: str):
    """Raise ManifestError if value is None or empty, otherwise return value."""
    if value is None or value == "":
        raise ManifestError(f"Missing required key: {key}")
    return value


def _require_object_name_suffix(value, key: str) -> str:
    suffix = str(_require(value, key)).strip()
    if not OBJECT_NAME_SUFFIX_PATTERN.fullmatch(suffix):
        raise ManifestError(
            f"Invalid {key}:"
            f"must contain only uppercase letters, digits, and underscores"
        )
    if suffix.startswith(RESERVED_OBJECT_NAME_PREFIXES):
        raise ManifestError(
            f"Invalid {key}:"
            f"do not include Snowflake object prefixes in object_name_suffix"
        )
    return suffix


def _require_adls_path_prefix(value, key: str) -> str:
    prefix = str(_require(value, key)).strip()
    if prefix.startswith("/"):
        raise ManifestError(
            f"Invalid {key}: must not be an absolute path (no leading slash)"
        )
    prefix = prefix.strip("/")
    if not prefix:
        raise ManifestError(f"Invalid {key}: must not be empty")
    if ".." in prefix.split("/"):
        raise ManifestError(f"Invalid {key}: must not contain path traversal")
    if not ADLS_PATH_PREFIX_PATTERN.fullmatch(prefix):
        raise ManifestError(
            f"Invalid {key}: use only lowercase letters, digits, hyphens, underscores, "
            f"and forward slashes — no leading/trailing slashes"
        )
    return prefix


def load_manifests(manifest_root: Path) -> List[DatasetSeriesConfig]:
    """Load all dataset series manifests from the given root directory.

    Returns a list of DatasetSeriesConfig objects.
    """
    manifests: List[DatasetSeriesConfig] = []

    for file_path in sorted(manifest_root.glob("*.y*ml")):
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        if not raw:
            continue

        dataset_id = _require(raw.get("dataset_id"), "dataset_id")
        series_id = _require(raw.get("series_id"), "series_id")
        entry_url = _require(raw.get("entry_url"), "entry_url")

        pub_raw = raw.get("publication_date", {})
        publication_date = PublicationDateRule(
            source=_require(pub_raw.get("source"), "publication_date.source"),
            pattern=_require(pub_raw.get("pattern"), "publication_date.pattern"),
        )

        subject_period_raw = raw.get("subject_period")
        subject_period = None
        if subject_period_raw:
            subject_rules: List[SubjectPeriodRuleItem] = []
            raw_rules = subject_period_raw.get("rules")
            if raw_rules:
                for r_idx, rule in enumerate(raw_rules, start=1):
                    subject_rules.append(
                        SubjectPeriodRuleItem(
                            source=_require(
                                rule.get("source"),
                                f"subject_period.rules[{r_idx}].source",
                            ),
                            pattern=_require(
                                rule.get("pattern"),
                                f"subject_period.rules[{r_idx}].pattern",
                            ),
                        )
                    )
            else:
                # Backward-compatible single-rule form.
                subject_rules.append(
                    SubjectPeriodRuleItem(
                        source=_require(
                            subject_period_raw.get("source"), "subject_period.source"
                        ),
                        pattern=_require(
                            subject_period_raw.get("pattern"), "subject_period.pattern"
                        ),
                    )
                )

            subject_period = SubjectPeriodRule(rules=subject_rules)

        target_entries = raw.get("targets", [])
        if not target_entries:
            raise ManifestError(f"{file_path.name}: targets must not be empty")

        targets: List[TargetConfig] = []
        for idx, target in enumerate(target_entries, start=1):
            target_id = _require(
                target.get("sub_dataset_id"), f"targets[{idx}].sub_dataset_id"
            )
            object_name_suffix = _require_object_name_suffix(
                target.get("object_name_suffix"),
                f"targets[{idx}].object_name_suffix",
            )
            adls_path_prefix = _require_adls_path_prefix(
                target.get("adls_path_prefix"),
                f"targets[{idx}].adls_path_prefix",
            )
            source_pages: List[SourcePageConfig] = []
            for p_idx, page in enumerate(target.get("source_pages", []), start=1):
                page_url = _require(
                    page.get("page_url"),
                    f"targets[{idx}].source_pages[{p_idx}].page_url",
                )

                steps: List[ScrapeStep] = []
                for s_idx, step in enumerate(page.get("scrape_steps", []), start=1):
                    steps.append(
                        ScrapeStep(
                            link_selector=_require(
                                step.get("link_selector"),
                                f"targets[{idx}].source_pages[{p_idx}].scrape_steps[{s_idx}].link_selector",
                            ),
                            text_filter=step.get("text_filter"),
                            file_extensions=step.get("file_extensions", []),
                        )
                    )

                if not steps:
                    raise ManifestError(
                        f"{file_path.name}: target {target_id} source_page "
                        f"{p_idx} has no scrape_steps"
                    )

                sibling_raw = page.get("sibling_discovery", {}) or {}
                source_pages.append(
                    SourcePageConfig(
                        page_url=page_url,
                        page_role=page.get("page_role", "default"),
                        partitioning_strategy=page.get("partitioning_strategy", "none"),
                        scrape_steps=steps,
                        sibling_discovery=SiblingDiscoveryConfig(
                            enabled=bool(sibling_raw.get("enabled", False)),
                            link_selector=str(
                                sibling_raw.get("link_selector", "a[href]")
                            ),
                            url_pattern=sibling_raw.get("url_pattern"),
                            text_pattern=sibling_raw.get("text_pattern"),
                            max_pages=int(sibling_raw.get("max_pages", 25)),
                        ),
                    )
                )

            legacy_steps: List[ScrapeStep] = []
            for s_idx, step in enumerate(target.get("scrape_steps", []), start=1):
                legacy_steps.append(
                    ScrapeStep(
                        link_selector=_require(
                            step.get("link_selector"),
                            f"targets[{idx}].scrape_steps[{s_idx}].link_selector",
                        ),
                        text_filter=step.get("text_filter"),
                        file_extensions=step.get("file_extensions", []),
                    )
                )

            if source_pages and legacy_steps:
                raise ManifestError(
                    (
                        f"{file_path.name}: target {target_id} must not define "
                        "both source_pages and scrape_steps"
                    )
                )
            if not source_pages and not legacy_steps:
                raise ManifestError(
                    (
                        f"{file_path.name}: target {target_id} must define "
                        "source_pages or scrape_steps"
                    )
                )

            if source_pages:
                normalized_source_pages = source_pages
                normalized_steps: List[ScrapeStep] = []
            else:
                normalized_source_pages = [
                    SourcePageConfig(
                        page_url=entry_url,
                        page_role="default",
                        partitioning_strategy="none",
                        scrape_steps=legacy_steps,
                    )
                ]
                normalized_steps = legacy_steps

            targets.append(
                TargetConfig(
                    sub_dataset_id=target_id,
                    object_name_suffix=object_name_suffix,
                    adls_path_prefix=adls_path_prefix,
                    scrape_steps=normalized_steps,
                    source_pages=normalized_source_pages,
                    compression=target.get("compression"),
                    excel_sheet=target.get("excel_sheet"),
                    delimiter=target.get("delimiter", ","),
                    encoding=target.get("encoding", "utf-8"),
                    reporting_period_columns=target.get("reporting_period_columns", []),
                    page_date_selectors=target.get("page_date_selectors", []),
                    period_coverage=(
                        PeriodCoverageHint(
                            file_scope=PeriodCoverageFileScopeHint(
                                duration_type=(
                                    target.get("period_coverage", {})
                                    .get("file_scope", {})
                                    .get(
                                        "duration_type",
                                        target.get("period_coverage", {}).get(
                                            "type", "unknown"
                                        ),
                                    )
                                ),
                                duration_value=(
                                    target.get("period_coverage", {})
                                    .get("file_scope", {})
                                    .get("duration_value")
                                ),
                                duration_unit=(
                                    target.get("period_coverage", {})
                                    .get("file_scope", {})
                                    .get("duration_unit")
                                ),
                                fiscal_year_start_month=(
                                    target.get("period_coverage", {})
                                    .get("file_scope", {})
                                    .get(
                                        "fiscal_year_start_month",
                                        target.get("period_coverage", {}).get(
                                            "fiscal_year_start_month"
                                        ),
                                    )
                                ),
                            ),
                            breakdown_granularity=target.get(
                                "period_coverage", {}
                            ).get("breakdown_granularity", []),
                        )
                        if target.get("period_coverage")
                        else None
                    ),
                )
            )

        fallback_raw = raw.get("fallback", {})
        fallback = FallbackConfig(
            allow_manual_acquisition=fallback_raw.get("allow_manual_acquisition", True),
            manual_drop_path=fallback_raw.get("manual_drop_path", "manual"),
            max_auto_retries=int(fallback_raw.get("max_auto_retries", 3)),
            timeout_threshold_minutes=int(
                fallback_raw.get("timeout_threshold_minutes", 5)
            ),
        )

        manifests.append(
            DatasetSeriesConfig(
                dataset_id=dataset_id,
                series_id=series_id,
                entry_url=entry_url,
                publication_date=publication_date,
                targets=targets,
                subject_period=subject_period,
                fallback=fallback,
            )
        )

    return manifests
