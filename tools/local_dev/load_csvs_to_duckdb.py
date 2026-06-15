"""Load local ingestion artifacts into dbt-compatible DuckDB ingest tables."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

try:
    from function_app.src.manifest_loader import load_manifests
except Exception:
    load_manifests = None

try:
    import duckdb
except ImportError:
    duckdb = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _as_posix(path: Path) -> str:
    return path.as_posix().replace("\\", "/")


def _qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _fq(schema: str, table: str) -> str:
    return f"{_qident(schema)}.{_qident(table)}"


def _execute_with_encoding_retry(con, sql, params, csv_path: Path):
    encodings = [
        "utf-8",  # default encoding
        "cp1252",  # Windows-1252 encoding
        "latin-1",  # ISO-8859-1 encoding
        "ascii",  # ASCII encoding
        "utf-16",  # UTF-16 encoding
        "utf-16le",  # UTF-16 Little Endian encoding
        "utf-16be",  # UTF-16 Big Endian encoding
        "utf-32",  # UTF-32 encoding
        "utf-32le",  # UTF-32 Little Endian encoding
        "utf-32be",  # UTF-32 Big Endian encoding
    ]

    last_error = None
    for encoding in encodings:
        try:
            logger.info(
                "Attempting to execute SQL with encoding %s for file %s",
                encoding,
                csv_path,
            )
            con.execute(sql, params + [encoding])
            logger.info(
                "Successfully executed SQL with encoding %s for file %s",
                encoding,
                csv_path,
            )
            return encoding

        except Exception as ex:
            last_error = ex
            logger.warning(
                "Error executing SQL with encoding %s for file %s: %s. Retrying with next encoding.",  # noqa: E501
                encoding,
                csv_path,
                str(ex)[:200],  # Limit error message length
            )

    msg = (
        f"Failed to execute SQL with all attempted encodings for file {csv_path}."
        f" Last error: {str(last_error)[:200]}"
    )
    raise RuntimeError(msg)


def _create_schemas(con: duckdb.DuckDBPyConnection) -> None:
    for schema in ("INGEST", "RAW", "PRESENTATION"):
        con.execute(f"create schema if not exists {_qident(schema)}")


def _load_manifests(manifest_root: Path) -> list[Any]:
    if load_manifests is None:
        raise RuntimeError(
            "Could not import manifest loader. Ensure REPO_ROOT is on PYTHONPATH."
        )
    return load_manifests(manifest_root)


def _load_sidecar_index(local_root: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for path in local_root.rglob("_INGEST_METADATA.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as ex:
            logger.warning("Skipping unreadable sidecar %s: %s", path, ex)
            continue
        target = str(payload.get("_TARGET_PATH", "")).strip("/")
        if target:
            records[target] = payload
    return records


def _ensure_ingest_table_from_csv(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    csv_path: Path,
) -> None:
    relation = _fq("INGEST", table_name)
    con.execute(
        f"""
        create table if not exists {relation} as
        select
            cast(null as timestamp) as _INGESTED_AT,
            cast(null as varchar) as _SOURCE_FILE_PATH,
            cast(null as varchar) as _SOURCE_FILE_NAME,
            cast(null as bigint) as _FILE_ROW_NUMBER,
            cast(null as varchar) as _FILE_CONTENT_KEY,
            cast(null as varchar) as _ACQUISITION_METHOD,
            cast(null as varchar) as _FALLBACK_REASON,
            cast(null as varchar) as _LOAD_ID,
            *
        from read_csv_auto(?, header=true, all_varchar=true, encoding='utf-8')
        limit 0
        """,
        [str(csv_path)],
    )


def _insert_csv_rows(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    csv_path: Path,
    sidecar: dict[str, Any],
) -> int:
    relation = _fq("INGEST", table_name)
    ingested_at = sidecar.get("_INGESTED_AT") or sidecar.get("_DOWNLOADED_AT") or ""
    source_file_path = sidecar.get("_PAYLOAD_STAGE_PATH") or ""
    source_file_name = sidecar.get("_SOURCE_FILE_NAME") or csv_path.name
    file_content_key = sidecar.get("_FILE_CONTENT_KEY") or ""
    acquisition_method = sidecar.get("_ACQUISITION_METHOD") or "automated"
    fallback_reason = sidecar.get("_FALLBACK_REASON") or ""
    load_id = sidecar.get("_LOAD_ID") or file_content_key[:16]
    row_count = int(
        con.execute(
            "select count(*) from read_csv_auto(?, header=true, all_varchar=true, encoding='utf-8')",  # noqa: E501
            [str(csv_path)],
        ).fetchone()[0]
    )
    _execute_with_encoding_retry(
        con,
        f"""
        insert into {relation}
        select
            try_cast(? as timestamp) as _INGESTED_AT,
            ? as _SOURCE_FILE_PATH,
            ? as _SOURCE_FILE_NAME,
            row_number() over () as _FILE_ROW_NUMBER,
            ? as _FILE_CONTENT_KEY,
            ? as _ACQUISITION_METHOD,
            ? as _FALLBACK_REASON,
            ? as _LOAD_ID,
            *
        from read_csv_auto(?, header=true, all_varchar=true, encoding=?)
        """,
        [
            ingested_at,
            source_file_path,
            source_file_name,
            file_content_key,
            acquisition_method,
            fallback_reason,
            load_id,
            str(csv_path),
            # encoding appended by _execute_with_encoding_retry
        ],
        csv_path,
    )
    return row_count


def _load_ingest_tables(
    con: duckdb.DuckDBPyConnection,
    local_root: Path,
    manifest_root: Path,
) -> int:
    configs = _load_manifests(manifest_root)
    sidecar_by_target = _load_sidecar_index(local_root)
    loaded_rows = 0

    for config in configs:
        for target in config.targets:
            if not target.object_name_suffix or not target.adls_path_prefix:
                continue

            target_prefix = local_root / target.adls_path_prefix
            if not target_prefix.exists():
                continue

            table_name = f"INGEST_{target.object_name_suffix}"
            csv_files = sorted(
                path
                for path in target_prefix.rglob("*.csv")
                if "downloaded_at=" in _as_posix(path)
            )
            if not csv_files:
                continue

            logger.info("Loading %d files into INGEST.%s", len(csv_files), table_name)
            _ensure_ingest_table_from_csv(con, table_name, csv_files[0])

            for csv_path in csv_files:
                rel_target = _as_posix(csv_path.relative_to(local_root)).strip("/")
                sidecar = sidecar_by_target.get(rel_target, {})
                loaded_rows += _insert_csv_rows(con, table_name, csv_path, sidecar)

    return loaded_rows


def _load_sidecar_table(con: duckdb.DuckDBPyConnection, local_root: Path) -> int:
    relation = _fq("INGEST", "INGEST_METADATA")
    con.execute(
        f"""
        create table if not exists {relation} (
            _CONTRACT_VERSION varchar,
            _DOWNLOADED_AT varchar,
            _INGESTED_AT varchar,
            _SOURCE_FILE_PATH varchar,
            _SOURCE_FILE_NAME varchar,
            _FILE_CONTENT_KEY varchar,
            _SUBJECT_PERIOD_FROM varchar,
            _SUBJECT_PERIOD_TO varchar,
            _SUBJECT_PERIOD_COVERAGE_TYPE varchar,
            _SUBJECT_PERIOD_INFERENCE_METHOD varchar,
            _SUBJECT_PERIOD_INFERENCE_SOURCE varchar,
            _SUBJECT_PERIOD_INFERENCE_CONFIDENCE varchar,
            _FILE_SCOPE_DURATION_TYPE varchar,
            _FILE_SCOPE_DURATION_VALUE bigint,
            _FILE_SCOPE_DURATION_UNIT varchar,
            _FILE_SCOPE_FISCAL_YEAR_START_MONTH bigint,
            _BREAKDOWN_GRANULARITY varchar,
            _PUBLICATION_DATE varchar,
            _PUBLICATION_DATE_SOURCE varchar,
            _ACQUISITION_METHOD varchar,
            _FALLBACK_REASON varchar,
            _LOAD_ID varchar,
            _SERIES_ID varchar,
            _SUB_DATASET_ID varchar,
            _TARGET_PATH varchar,
            _PAYLOAD_STAGE_PATH varchar,
            _SOURCE_ETAG varchar,
            _SOURCE_LAST_MODIFIED varchar
        )
        """
    )
    con.execute(f"delete from {relation}")

    rows_loaded = 0
    for sidecar in local_root.rglob("_INGEST_METADATA.json"):
        try:
            record = json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception as ex:
            logger.warning("Skipping unreadable sidecar %s: %s", sidecar, ex)
            continue

        con.execute(
            f"""
            insert into {relation} values (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                record.get("_CONTRACT_VERSION", ""),
                record.get("_DOWNLOADED_AT", ""),
                record.get("_INGESTED_AT", ""),
                record.get("_SOURCE_FILE_PATH", ""),
                record.get("_SOURCE_FILE_NAME", ""),
                record.get("_FILE_CONTENT_KEY", ""),
                record.get("_SUBJECT_PERIOD_FROM", ""),
                record.get("_SUBJECT_PERIOD_TO", ""),
                record.get("_SUBJECT_PERIOD_COVERAGE_TYPE", ""),
                record.get("_SUBJECT_PERIOD_INFERENCE_METHOD", ""),
                record.get("_SUBJECT_PERIOD_INFERENCE_SOURCE", ""),
                record.get("_SUBJECT_PERIOD_INFERENCE_CONFIDENCE", ""),
                record.get("_FILE_SCOPE_DURATION_TYPE", ""),
                record.get("_FILE_SCOPE_DURATION_VALUE") or None,
                record.get("_FILE_SCOPE_DURATION_UNIT", ""),
                record.get("_FILE_SCOPE_FISCAL_YEAR_START_MONTH") or None,
                record.get("_BREAKDOWN_GRANULARITY", ""),
                record.get("_PUBLICATION_DATE", ""),
                record.get("_PUBLICATION_DATE_SOURCE", ""),
                record.get("_ACQUISITION_METHOD", ""),
                record.get("_FALLBACK_REASON", ""),
                record.get("_LOAD_ID", ""),
                record.get("_SERIES_ID", ""),
                record.get("_SUB_DATASET_ID", ""),
                record.get("_TARGET_PATH", ""),
                record.get("_PAYLOAD_STAGE_PATH", ""),
                record.get("_SOURCE_ETAG", ""),
                record.get("_SOURCE_LAST_MODIFIED", ""),
            ],
        )
        rows_loaded += 1

    return rows_loaded


def _load_telemetry_table(con: duckdb.DuckDBPyConnection, local_root: Path) -> int:
    relation = _fq("INGEST", "INGEST_FUNCTION_APP_EVENTS")
    con.execute(
        f"""
        create table if not exists {relation} (
            EVENT_TIMESTAMP_UTC timestamp,
            RUN_ID varchar,
            CONTRACT_VERSION varchar,
            STAGE varchar,
            STATUS varchar,
            ATTEMPT_NUMBER bigint,
            SERIES_ID varchar,
            SUB_DATASET_ID varchar,
            SOURCE_URL varchar,
            FILE_NAME varchar,
            SOURCE_CONTENT_HASH varchar,
            LOAD_ID varchar,
            SOURCE_BYTES bigint,
            RAW_ROW_COUNT bigint,
            NORMALIZED_ROW_COUNT bigint,
            NORMALIZED_BYTES bigint,
            UPLOADED_PATH varchar,
            SKIP_REASON varchar,
            ACQUISITION_METHOD varchar,
            DURATION_MS bigint,
            ERROR_TYPE varchar,
            ERROR_MESSAGE varchar,
            DISCOVERED_FILE_COUNT bigint
        )
        """
    )
    con.execute(f"delete from {relation}")

    rows_loaded = 0
    telemetry_files = sorted(local_root.rglob("*.jsonl"))
    for telemetry_file in telemetry_files:
        rel = _as_posix(telemetry_file.relative_to(local_root))
        if "_telemetry/function_app_events/" not in rel:
            continue
        row_count = int(
            con.execute(
                "select count(*) from read_json_auto(?, format='newline_delimited')",
                [str(telemetry_file)],
            ).fetchone()[0]
        )
        con.execute(
            f"""
            insert into {relation}
            select
                try_cast(event_timestamp_utc as timestamp) as EVENT_TIMESTAMP_UTC,
                run_id as RUN_ID,
                contract_version as CONTRACT_VERSION,
                stage as STAGE,
                status as STATUS,
                try_cast(attempt_number as bigint) as ATTEMPT_NUMBER,
                series_id as SERIES_ID,
                sub_dataset_id as SUB_DATASET_ID,
                source_url as SOURCE_URL,
                file_name as FILE_NAME,
                source_content_hash as SOURCE_CONTENT_HASH,
                load_id as LOAD_ID,
                try_cast(source_bytes as bigint) as SOURCE_BYTES,
                try_cast(raw_row_count as bigint) as RAW_ROW_COUNT,
                try_cast(normalized_row_count as bigint) as NORMALIZED_ROW_COUNT,
                try_cast(normalized_bytes as bigint) as NORMALIZED_BYTES,
                uploaded_path as UPLOADED_PATH,
                skip_reason as SKIP_REASON,
                acquisition_method as ACQUISITION_METHOD,
                try_cast(duration_ms as bigint) as DURATION_MS,
                error_type as ERROR_TYPE,
                error_message as ERROR_MESSAGE,
                try_cast(discovered_file_count as bigint) as DISCOVERED_FILE_COUNT
            from read_json_auto(?, format='newline_delimited')
            """,
            [str(telemetry_file)],
        )
        rows_loaded += row_count

    return rows_loaded


def _load_artifacts(local_root: Path, manifest_root: Path, duckdb_path: Path) -> int:
    if duckdb is None:
        logger.error("DuckDB not installed. Run: pip install duckdb")
        return 1

    try:
        con = duckdb.connect(str(duckdb_path))
        _create_schemas(con)
        ingest_rows = _load_ingest_tables(con, local_root, manifest_root)
        sidecar_rows = _load_sidecar_table(con, local_root)
        # telemetry_rows = _load_telemetry_table(con, local_root)
        # TODO: mimic the ingestion telemetry table load
        telemetry_rows = 0  # TODO: mimic the ingestion telemetry table load
        logger.info(
            "Loaded ingest_rows=%d sidecar_rows=%d telemetry_rows=%d",
            ingest_rows,
            sidecar_rows,
            telemetry_rows,
        )
        con.close()
        return 0
    except Exception as ex:
        logger.error("Error loading local artifacts to DuckDB: %s", ex)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load local ingestion artifacts into dbt-compatible DuckDB tables."
    )
    parser.add_argument(
        "--local-root",
        type=Path,
        default=Path(".") / ".local_adls",
        help="Local ADLS root directory (default: .local_adls)",
    )
    parser.add_argument(
        "--manifest-root",
        type=Path,
        default=Path(os.environ.get("MANIFEST_ROOT", "config/datasets")),
        help="Manifest root directory used to map targets to ingest tables.",
    )
    parser.add_argument(
        "--duckdb-file",
        type=Path,
        default=None,
        help="DuckDB file path (default: LOCAL_STORAGE_ROOT/local_validation.duckdb)",
    )

    args = parser.parse_args()

    local_root = args.local_root.resolve()
    if not local_root.exists():
        logger.error("Local root does not exist: %s", local_root)
        return 1

    manifest_root = args.manifest_root.resolve()
    if not manifest_root.exists():
        logger.error("Manifest root does not exist: %s", manifest_root)
        return 1

    duckdb_file = args.duckdb_file
    if not duckdb_file:
        duckdb_file = local_root / "local_validation.duckdb"

    logger.info("Loading local artifacts from: %s", local_root)
    logger.info("Manifest root: %s", manifest_root)
    logger.info("DuckDB destination: %s", duckdb_file)

    return _load_artifacts(local_root, manifest_root, duckdb_file)


if __name__ == "__main__":
    raise SystemExit(main())
