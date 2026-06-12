from __future__ import annotations

import json
from pathlib import Path

from tools.local_dev import verify_local_run


def test_build_report_counts_files_and_sidecars(tmp_path: Path):
    local_root = tmp_path / "local_adls"
    data_dir = local_root / "series-a" / "sub-a" / "downloaded_at=20260101T000000"
    data_dir.mkdir(parents=True)

    csv_path = data_dir / "sample.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")

    sidecar_path = data_dir / "_INGEST_METADATA.json"
    sidecar_path.write_text(
        json.dumps({"_SOURCE_FILE_PATH": "https://example.test/file.csv"}),
        encoding="utf-8",
    )

    report = verify_local_run._build_report(
        local_root=local_root,
        duckdb_path=local_root / "local_validation.duckdb",
    )

    assert report["csv_file_count"] == 1
    assert report["sidecar_file_count"] == 1
    assert report["files_by_series_sub_dataset"] == [
        {
            "series_id": "series-a",
            "sub_dataset_id": "sub-a",
            "csv_file_count": 1,
        }
    ]


def test_write_reports_outputs_json_and_markdown(tmp_path: Path):
    report = {
        "generated_at_utc": "2026-06-12T00:00:00Z",
        "local_root": str(tmp_path),
        "csv_file_count": 0,
        "sidecar_file_count": 0,
        "files_by_series_sub_dataset": [],
        "sidecar_source_url_count": 0,
        "csv_path_sample": [],
        "duckdb": {
            "path": str(tmp_path / "x.duckdb"),
            "database_exists": False,
            "duckdb_available": False,
            "table_count": 0,
            "tables": [],
        },
        "observations": {
            "csv_without_sidecar_possible": False,
            "sidecar_without_csv_possible": False,
            "csv_file_path_count": 0,
        },
    }

    json_path, md_path = verify_local_run._write_reports(
        report=report,
        report_dir=tmp_path,
        report_prefix="summary",
    )

    assert json_path.exists()
    assert md_path.exists()
    assert "Local Run Verification Summary" in md_path.read_text(encoding="utf-8")
