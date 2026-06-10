from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

import pytest

from tests.dbt_macro_harness import render_alias_select_sql, require_dbt

duckdb = pytest.importorskip("duckdb")


def _expected_aliases_from_sql(select_sql: str) -> list[str]:
    return re.findall(r'as\s+"([^"]+)"', select_sql)


def _run_web_manifest_to_duckdb(tmp_path, monkeypatch, manifest_name: str):
    from function_app.src.run_ingestion import execute_ingestion

    require_dbt()

    fixture_root = Path(__file__).resolve().parent / "fixtures" / "manifests"
    manifest_root = tmp_path / "manifests"
    local_root = tmp_path / "local_adls"
    query_duckdb_path = Path(
        os.environ.get("DUCKDB_FILE", tmp_path / "integration.duckdb")
    )
    macro_duckdb_path = tmp_path / "macro_render.duckdb"
    query_duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fixture_root / manifest_name, manifest_root / manifest_name)

    monkeypatch.setenv("LOCAL_STORAGE_MODE", "true")
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(local_root))
    monkeypatch.setenv("MANIFEST_ROOT", str(manifest_root))
    monkeypatch.setenv("MANUAL_INPUT_PREFIX", "manual")

    result = execute_ingestion()
    assert result["uploaded"]

    csv_files = [
        path
        for path in local_root.rglob("*.csv")
        if "downloaded_at=" in path.as_posix()
    ]
    assert csv_files, "Expected at least one landed CSV file"

    csv_path = csv_files[0]
    metadata_path = csv_path.parent / "_INGEST_METADATA.json"
    assert metadata_path.exists(), "Expected metadata sidecar file"

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert "_DOWNLOADED_AT" in metadata, "Expected _DOWNLOADED_AT in sidecar metadata"
    con = duckdb.connect(str(query_duckdb_path))

    con.execute("drop table if exists raw_data")
    con.execute("drop view if exists presentation_view")
    con.execute("drop view if exists max_publication_view")
    con.execute("drop view if exists current_revision_view")
    con.execute(
        "create table raw_data as select * from "
        "read_csv_auto(?, header=true, all_varchar=true)",
        [str(csv_path)],
    )
    con.execute("alter table raw_data add column _PUBLICATION_DATE varchar")
    con.execute("alter table raw_data add column _SOURCE_FILE_PATH varchar")
    con.execute(
        "update raw_data set _PUBLICATION_DATE = ?, _SOURCE_FILE_PATH = ?",
        [metadata["_PUBLICATION_DATE"], metadata["_SOURCE_FILE_PATH"]],
    )

    raw_columns = [
        row[1] for row in con.execute("PRAGMA table_info('raw_data')").fetchall()
    ]
    assert [column for column in raw_columns if not column.startswith("_")]

    select_sql = render_alias_select_sql(raw_columns, macro_duckdb_path)
    con.execute(f"create view presentation_view as select {select_sql} from raw_data")

    presentation_columns = [
        row[1]
        for row in con.execute("PRAGMA table_info('presentation_view')").fetchall()
    ]
    expected_aliases = _expected_aliases_from_sql(select_sql)
    assert presentation_columns == expected_aliases

    reporting_column = next(
        alias for alias in expected_aliases if not alias.startswith("_")
    )
    con.execute(
        f"""
        create view max_publication_view as
        select {reporting_column}, max(_PUBLICATION_DATE) as MAX_PUBLICATION_DATE
        from presentation_view
        group by {reporting_column}
        """
    )
    con.execute(
        f"""
        create view current_revision_view as
        select src.*
        from presentation_view src
        join max_publication_view mx
          on src.{reporting_column} = mx.{reporting_column}
         and src._PUBLICATION_DATE = mx.MAX_PUBLICATION_DATE
        """
    )

    assert con.execute("select count(*) from raw_data").fetchone()[0] > 0
    assert con.execute("select count(*) from presentation_view").fetchone()[0] > 0
    assert con.execute("select count(*) from max_publication_view").fetchone()[0] > 0
    assert con.execute("select count(*) from current_revision_view").fetchone()[0] > 0

    return {
        "csv_path": csv_path,
        "metadata": metadata,
        "presentation_columns": presentation_columns,
    }


@pytest.mark.skipif(
    os.environ.get("RUN_WEB_E2E", "false").lower() not in {"1", "true", "yes"},
    reason="Set RUN_WEB_E2E=true to run web-backed integration test.",
)
def test_web_download_to_duckdb_e2e(tmp_path, monkeypatch):
    result = _run_web_manifest_to_duckdb(
        tmp_path, monkeypatch, "web_restrictive_interventions_test.yaml"
    )
    assert result["csv_path"].suffix.lower() == ".csv"
    assert any(not column.startswith("_") for column in result["presentation_columns"])


@pytest.mark.skipif(
    os.environ.get("RUN_WEB_E2E", "false").lower() not in {"1", "true", "yes"},
    reason="Set RUN_WEB_E2E=true to run web-backed integration test.",
)
def test_web_xlsx_download_to_duckdb_e2e(tmp_path, monkeypatch):
    result = _run_web_manifest_to_duckdb(
        tmp_path, monkeypatch, "web_chs_waiting_lists_xlsx_test.yaml"
    )
    assert result["csv_path"].suffix.lower() == ".csv"
    assert result["metadata"]["_SOURCE_FILE_PATH"].lower().endswith(".xlsx")
    assert any(
        "_" in column
        for column in result["presentation_columns"]
        if not column.startswith("_")
    )
