from __future__ import annotations

from pathlib import Path

from function_app.src import run_ingestion
from function_app.src.models import (
    DatasetSeriesConfig,
    DiscoveredFile,
    PublicationDateRule,
)


def _config(dataset_id: str) -> DatasetSeriesConfig:
    return DatasetSeriesConfig(
        dataset_id=dataset_id,
        series_id=dataset_id,
        entry_url="https://example.test",
        publication_date=PublicationDateRule(source="link_text", pattern=r"(\\d{8})"),
        targets=[],
    )


def _file(
    sub_dataset_id: str, source_url: str, publication_date: str
) -> DiscoveredFile:
    return DiscoveredFile(
        dataset_id="dataset-a",
        series_id="series-a",
        sub_dataset_id=sub_dataset_id,
        source_url=source_url,
        publication_date_value=publication_date,
        link_text="sample",
    )


def test_filter_configs_profile_and_env(monkeypatch, tmp_path: Path):
    profile = tmp_path / "local.profile.env"
    profile.write_text(
        "INCLUDE_DATASET_IDS=dataset-a,dataset-b\nEXCLUDE_DATASET_IDS=dataset-b\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("LOCAL_DATASET_PROFILE_FILE", str(profile))
    monkeypatch.setenv("INCLUDE_DATASET_IDS", "dataset-c")

    configs = [_config("dataset-a"), _config("dataset-b"), _config("dataset-c")]
    filtered = run_ingestion._filter_configs(configs)

    assert [item.dataset_id for item in filtered] == ["dataset-a", "dataset-c"]


def test_apply_discovery_limits_respects_caps():
    discovered = [
        _file("target-1", "https://example.test/a", "20250101"),
        _file("target-1", "https://example.test/b", "20240101"),
        _file("target-2", "https://example.test/c", "20260101"),
    ]

    selected = run_ingestion._apply_discovery_limits(
        discovered,
        dataset_limit=2,
        target_limit=1,
        total_remaining=2,
    )

    # newest-first ordering then per-target cap should keep target-2 and target-1 newest
    assert [(item.sub_dataset_id, item.source_url) for item in selected] == [
        ("target-2", "https://example.test/c"),
        ("target-1", "https://example.test/a"),
    ]


def test_execution_mode_invalid_defaults_full(monkeypatch):
    monkeypatch.setenv("INGEST_EXECUTION_MODE", "not-a-mode")
    assert run_ingestion._execution_mode() == "full"
