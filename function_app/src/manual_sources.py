from __future__ import annotations

import re
from typing import List

from .adls_writer import list_blob_paths
from .datetime_utils import normalize_datetime_value, normalize_subject_period_value
from .models import DatasetSeriesConfig, DiscoveredFile, TargetConfig


def discover_manual_files(
    config: DatasetSeriesConfig, target: TargetConfig, manual_prefix: str
) -> List[DiscoveredFile]:
    """Discover manually dropped files for a dataset/target.

    Matches expected file types and extracts publication dates from filenames.
    """
    prefix = manual_prefix.strip("/")
    search_prefix = (
        f"{prefix}/{config.series_id}/{target.sub_dataset_id}/"
        if prefix
        else f"{config.series_id}/{target.sub_dataset_id}/"
    )
    blob_paths = list_blob_paths(search_prefix)

    discovered: List[DiscoveredFile] = []
    for blob_path in sorted(blob_paths):
        lowered = blob_path.lower()
        if not lowered.endswith((".csv", ".zip", ".xlsx", ".xls")):
            continue

        candidate_name = blob_path.split("/")[-1]
        source_value = candidate_name
        match = re.search(
            config.publication_date.pattern, source_value, flags=re.IGNORECASE
        )
        if match:
            publication_date = "_".join(
                group for group in match.groups() if group
            ) or match.group(0)
            publication_date = normalize_datetime_value(publication_date)
        else:
            publication_date = None

        subject_period = None
        if config.subject_period:
            subject_match = re.search(
                config.subject_period.pattern, source_value, flags=re.IGNORECASE
            )
            if subject_match:
                subject_raw = "_".join(
                    group for group in subject_match.groups() if group
                ) or subject_match.group(0)
                subject_period = normalize_subject_period_value(subject_raw)

        discovered.append(
            DiscoveredFile(
                dataset_id=config.dataset_id,
                series_id=config.series_id,
                sub_dataset_id=target.sub_dataset_id,
                source_url=blob_path,
                publication_date_value=publication_date,
                link_text=candidate_name,
                subject_period_value=subject_period,
            )
        )

    return discovered
