from __future__ import annotations

import json
from pathlib import Path

from function_app.src.datetime_utils import (
    extract_datetime_from_pattern,
    extract_page_publication_datetime,
)
from function_app.src.models import (
    DatasetSeriesConfig,
    DiscoveredFile,
    FallbackConfig,
    PublicationDateRule,
    ScrapeStep,
    TargetConfig,
)
from function_app.src.run_ingestion import CONTRACT_VERSION, execute_ingestion


def test_pattern_datetime_normalization_uses_midnight_when_time_missing():
    extracted = extract_datetime_from_pattern(r"(March 2026)", "Performance March 2026")
    assert extracted == "20260301T000000"


def test_page_publication_datetime_prefers_published_or_last_updated():
    page_text = "Some page text. Last updated: 15 May 2024 More text."
    extracted = extract_page_publication_datetime(page_text)
    assert extracted == "20240515T000000"


def test_execute_ingestion_skips_redownload_and_reupload_when_source_unchanged(
    monkeypatch,
):
    storage: dict[str, bytes] = {}
    normalize_call_count = {"count": 0}

    config = DatasetSeriesConfig(
        dataset_id="mh",
        series_id="mental-health-services-monthly-statistics",
        entry_url="https://example.com",
        publication_date=PublicationDateRule(
            source="link_text", pattern=r"(March 2026)"
        ),
        targets=[
            TargetConfig(
                sub_dataset_id="restrictive-interventions",
                scrape_steps=[ScrapeStep(link_selector="a[href]")],
            )
        ],
        fallback=FallbackConfig(allow_manual_acquisition=False),
    )

    discovered = DiscoveredFile(
        dataset_id="mh",
        series_id="mental-health-services-monthly-statistics",
        sub_dataset_id="restrictive-interventions",
        source_url="https://example.com/restrictive.zip",
        publication_date_value=None,
        link_text="Restrictive Interventions",
    )

    def fake_upload_bytes(path_in_container: str, payload: bytes) -> None:
        storage[path_in_container] = payload

    def fake_list_blob_paths(prefix: str):
        return [path for path in storage if path.startswith(prefix)]

    def fake_download_blob_bytes(blob_path: str) -> bytes:
        return storage[blob_path]

    def fake_normalize_to_csv(file_url: str):
        normalize_call_count["count"] += 1
        return "restrictive.csv", b"A,B\n1,2\n", "hash-123"

    monkeypatch.setattr(
        "function_app.src.run_ingestion.load_manifests", lambda _: [config]
    )
    monkeypatch.setattr(
        "function_app.src.run_ingestion.discover_files", lambda _config: [discovered]
    )
    monkeypatch.setattr(
        "function_app.src.run_ingestion.normalize_to_csv", fake_normalize_to_csv
    )
    monkeypatch.setattr(
        "function_app.src.run_ingestion.upload_bytes", fake_upload_bytes
    )
    monkeypatch.setattr(
        "function_app.src.run_ingestion.list_blob_paths", fake_list_blob_paths
    )
    monkeypatch.setattr(
        "function_app.src.run_ingestion.download_blob_bytes", fake_download_blob_bytes
    )
    monkeypatch.setattr(
        "function_app.src.run_ingestion._get_source_headers",
        lambda _url: ("etag-1", "Wed, 21 May 2026 10:19:00 GMT"),
    )
    monkeypatch.setattr(
        "function_app.src.run_ingestion.now_utc_compact", lambda: "20260521T101900"
    )
    monkeypatch.setenv("MANIFEST_ROOT", str(Path(".").resolve()))

    first_result = execute_ingestion()
    assert len(first_result["uploaded"]) == 1
    assert normalize_call_count["count"] == 1

    metadata_path = (
        "mental-health-services-monthly-statistics/restrictive-interventions/"
        "subject_period=202605/"
        "publication_date=20260521T101900/_INGEST_METADATA.json"
    )
    assert metadata_path in storage
    metadata = json.loads(storage[metadata_path].decode("utf-8"))
    assert metadata["_CONTRACT_VERSION"] == CONTRACT_VERSION
    assert metadata["_SOURCE_ETAG"] == "etag-1"

    second_result = execute_ingestion()
    assert second_result["uploaded"] == []
    assert normalize_call_count["count"] == 1
