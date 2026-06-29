from __future__ import annotations

from pathlib import Path

import pytest

from function_app.src.models import (
    DatasetSeriesConfig,
    PublicationDateRule,
    TargetConfig,
)
from tools.local_dev import load_csvs_to_duckdb

duckdb = pytest.importorskip("duckdb")


def _write_csv(local_root: Path, adls_path_prefix: str, columns: list[str]) -> None:
    data_dir = local_root / adls_path_prefix / "downloaded_at=20260101T000000"
    data_dir.mkdir(parents=True)
    header = ",".join(columns)
    (data_dir / "sample.csv").write_text(f"{header}\n1,2\n", encoding="utf-8")


def _make_config() -> DatasetSeriesConfig:
    target = TargetConfig(
        sub_dataset_id="drift-target",
        object_name_suffix="TEST_DRIFT_SAMPLE",
        adls_path_prefix="drift-dataset/drift-target",
    )
    return DatasetSeriesConfig(
        dataset_id="drift-dataset",
        series_id="drift-series",
        entry_url="https://example.test/drift",
        publication_date=PublicationDateRule(source="link_text", pattern="."),
        targets=[target],
    )


def test_load_ingest_tables_records_drift_warning(tmp_path, monkeypatch):
    local_root = tmp_path / "local_adls"
    _write_csv(local_root, "drift-dataset/drift-target", ["ColA", "ColX"])

    schema_root = tmp_path / "schemas"
    schema_root.mkdir()
    (schema_root / "drift-dataset.yaml").write_text(
        "schemas:\n  TEST_DRIFT_SAMPLE:\n    columns: [ColA, ColB, ColC]\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        load_csvs_to_duckdb, "_load_manifests", lambda manifest_root: [_make_config()]
    )

    con = duckdb.connect(":memory:")
    load_csvs_to_duckdb._create_schemas(con)

    result = load_csvs_to_duckdb._load_ingest_tables(
        con, local_root, tmp_path / "unused-manifest-root", schema_root, 0.20
    )

    assert result.failures == []
    assert result.loaded_rows == 1
    assert len(result.drift_warnings) == 1
    assert result.drift_warnings[0].table_name == "TEST_DRIFT_SAMPLE"
    assert result.drift_warnings[0].drift_ratio == 0.75


def test_load_ingest_tables_no_drift_warning_when_schema_missing(tmp_path, monkeypatch):
    local_root = tmp_path / "local_adls"
    _write_csv(local_root, "drift-dataset/drift-target", ["ColA", "ColX"])

    monkeypatch.setattr(
        load_csvs_to_duckdb, "_load_manifests", lambda manifest_root: [_make_config()]
    )

    con = duckdb.connect(":memory:")
    load_csvs_to_duckdb._create_schemas(con)

    result = load_csvs_to_duckdb._load_ingest_tables(
        con,
        local_root,
        tmp_path / "unused-manifest-root",
        tmp_path / "no-schemas",
        0.20,
    )

    assert result.failures == []
    assert result.drift_warnings == []
