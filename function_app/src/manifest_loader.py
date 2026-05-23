from __future__ import annotations

from pathlib import Path
from typing import List

import yaml

from .models import (
    DatasetSeriesConfig,
    FallbackConfig,
    PublicationDateRule,
    ScrapeStep,
    SubjectPeriodRule,
    SubjectPeriodRuleItem,
    TargetConfig,
)


class ManifestError(Exception):
    """Custom exception for manifest loading errors."""

    pass


def _require(value, key: str):
    """Raise ManifestError if value is None or empty, otherwise return value."""
    if value is None or value == "":
        raise ManifestError(f"Missing required key: {key}")
    return value


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
            steps: List[ScrapeStep] = []
            for s_idx, step in enumerate(target.get("scrape_steps", []), start=1):
                steps.append(
                    ScrapeStep(
                        link_selector=_require(
                            step.get("link_selector"),
                            f"targets[{idx}].scrape_steps[{s_idx}].link_selector",
                        ),
                        text_filter=step.get("text_filter"),
                        file_extensions=step.get("file_extensions", []),
                    )
                )

            if not steps:
                raise ManifestError(
                    f"{file_path.name}: target {target_id} has no scrape_steps"
                )

            targets.append(
                TargetConfig(
                    sub_dataset_id=target_id,
                    scrape_steps=steps,
                    compression=target.get("compression"),
                    excel_sheet=target.get("excel_sheet"),
                    delimiter=target.get("delimiter", ","),
                    encoding=target.get("encoding", "utf-8"),
                    reporting_period_columns=target.get("reporting_period_columns", []),
                    page_date_selectors=target.get("page_date_selectors", []),
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
