"""Load local ingestion artifacts into dbt-compatible DuckDB ingest tables."""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass, field
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

ENCODINGS = [
    "utf-8",
    "cp1252",
    "latin-1",
    "ascii",
    "utf-16",
    "utf-16le",
    "utf-16be",
    "utf-32",
    "utf-32le",
    "utf-32be",
]

# Errors with these markers indicate a genuine SQL/schema problem (e.g. a
# column-count mismatch) rather than a decode failure, so retrying with a
# different encoding will never fix them.
_NON_ENCODING_ERROR_MARKERS = ("Binder Error", "Catalog Error")

READ_CSV_OPTS = "header=true, all_varchar=true, quote='\"', hive_partitioning=false"


@dataclass
class LoadFailure:
    table_name: str
    csv_path: Path
    error: str


@dataclass
class LoadResult:
    loaded_rows: int = 0
    failures: list[LoadFailure] = field(default_factory=list)


def _as_posix(path: Path) -> str:
    return path.as_posix().replace("\\", "/")


def _qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _fq(schema: str, table: str) -> str:
    return f"{_qident(schema)}.{_qident(table)}"


def _is_retryable_encoding_error(ex: Exception) -> bool:
    msg = str(ex)
    return not any(marker in msg for marker in _NON_ENCODING_ERROR_MARKERS)


def _detect_encoding(con, csv_path: Path) -> str:
    """Find the first encoding that lets DuckDB parse this file's header.

    Only probes schema (LIMIT 0), so this never reads the file's data twice.
    Stops immediately on a non-encoding error (e.g. a Binder Error) since no
    amount of encoding retrying will fix a schema/SQL problem.
    """
    last_error: Exception | None = None
    for encoding in ENCODINGS:
        try:
            con.execute(
                f"select * from read_csv_auto(?, {READ_CSV_OPTS}, encoding=?) limit 0",
                [str(csv_path), encoding],
            )
            return encoding
        except Exception as ex:
            if not _is_retryable_encoding_error(ex):
                raise
            last_error = ex
    msg = (
        f"Could not decode {csv_path} with any known encoding. "
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
    encoding: str,
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
        from read_csv_auto(?, {READ_CSV_OPTS}, encoding=?)
        limit 0
        """,
        [str(csv_path), encoding],
    )


def _table_columns(con: duckdb.DuckDBPyConnection, table_name: str) -> set[str]:
    rows = con.execute(
        "select column_name from information_schema.columns "
        "where table_schema = 'INGEST' and table_name = ?",
        [table_name],
    ).fetchall()
    return {r[0] for r in rows}


def _csv_columns(
    con: duckdb.DuckDBPyConnection, csv_path: Path, encoding: str
) -> list[str]:
    description = con.execute(
        (f"select * from read_csv_auto(?, {READ_CSV_OPTS}, encoding=?) limit 0"),
        [str(csv_path), encoding],
    ).description
    return [c[0] for c in description]


def _evolve_table_schema(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    csv_path: Path,
    encoding: str,
) -> None:
    """Add any column present in this file but missing from the table.

    Mirrors Snowpipe-style incremental schema evolution: each file is
    evaluated as it lands, new columns are added as nullable, and earlier
    rows simply read back NULL for columns that didn't exist yet.
    """
    existing = _table_columns(con, table_name)
    for column in _csv_columns(con, csv_path, encoding):
        if column not in existing:
            relation = _fq("INGEST", table_name)
            con.execute(f"alter table {relation} add column {_qident(column)} varchar")
            logger.info(
                "Schema evolution: %s gained column %r (from %s)",
                table_name,
                column,
                csv_path.name,
            )
            existing.add(column)


def _insert_csv_rows(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    csv_path: Path,
    sidecar: dict[str, Any],
    encoding: str,
) -> int:
    relation = _fq("INGEST", table_name)
    ingested_at = sidecar.get("_INGESTED_AT") or sidecar.get("_DOWNLOADED_AT") or ""
    source_file_path = sidecar.get("_PAYLOAD_STAGE_PATH") or ""
    source_file_name = sidecar.get("_SOURCE_FILE_NAME") or csv_path.name
    file_content_key = sidecar.get("_FILE_CONTENT_KEY") or ""
    acquisition_method = sidecar.get("_ACQUISITION_METHOD") or "automated"
    fallback_reason = sidecar.get("_FALLBACK_REASON") or ""
    load_id = sidecar.get("_LOAD_ID") or file_content_key[:16]

    result = con.execute(
        f"""
        insert into {relation} by name
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
        from read_csv_auto(?, {READ_CSV_OPTS}, encoding=?)
        returning 1
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
            encoding,
        ],
    )
    return len(result.fetchall())


def _load_one_file(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    csv_path: Path,
    sidecar_by_target: dict[str, dict[str, Any]],
    local_root: Path,
    table_created: bool,
) -> tuple[int, bool, str | None]:
    """Load a single CSV into the named ingest table.

    Returns (rows_loaded, table_created, error_message). On failure,
    rows_loaded is 0 and error_message is set; the caller is expected to log
    and continue with the next file rather than abort the run.
    """
    try:
        encoding = _detect_encoding(con, csv_path)
        if not table_created:
            _ensure_ingest_table_from_csv(con, table_name, csv_path, encoding)
            table_created = True
        else:
            _evolve_table_schema(con, table_name, csv_path, encoding)

        rel_target = _as_posix(csv_path.relative_to(local_root)).strip("/")
        sidecar = sidecar_by_target.get(rel_target, {})
        rows = _insert_csv_rows(con, table_name, csv_path, sidecar, encoding)
        suffix = "" if encoding == "utf-8" else f" (encoding={encoding})"
        logger.info("Loaded %s: %d rows%s", csv_path.name, rows, suffix)
        return rows, table_created, None
    except Exception as ex:
        message = str(ex)[:300]
        logger.warning("Failed to load %s: %s", csv_path.name, message)
        return 0, table_created, message


def _load_target_files(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    csv_files: list[Path],
    sidecar_by_target: dict[str, dict[str, Any]],
    local_root: Path,
    result: LoadResult,
) -> None:
    logger.info("Loading %d files into INGEST.%s", len(csv_files), table_name)
    table_created = False
    for csv_path in csv_files:
        rows, table_created, error = _load_one_file(
            con, table_name, csv_path, sidecar_by_target, local_root, table_created
        )
        if error is not None:
            result.failures.append(LoadFailure(table_name, csv_path, error))
        else:
            result.loaded_rows += rows


def _load_ingest_tables(
    con: duckdb.DuckDBPyConnection,
    local_root: Path,
    manifest_root: Path,
) -> LoadResult:
    configs = _load_manifests(manifest_root)
    sidecar_by_target = _load_sidecar_index(local_root)
    result = LoadResult()

    for config in configs:
        for target in config.targets:
            if not target.object_name_suffix or not target.adls_path_prefix:
                continue

            target_prefix = local_root / target.adls_path_prefix
            if target_prefix.exists():
                table_name = f"INGEST_{target.object_name_suffix}"
                csv_files = sorted(
                    path
                    for path in target_prefix.rglob("*.csv")
                    if "downloaded_at=" in _as_posix(path)
                )
                if csv_files:
                    _load_target_files(
                        con,
                        table_name,
                        csv_files,
                        sidecar_by_target,
                        local_root,
                        result,
                    )

            for sub_table in target.sub_tables:
                st_prefix = local_root / sub_table.adls_path_prefix
                if not st_prefix.exists():
                    continue
                st_table = f"INGEST_{sub_table.object_name_suffix}"
                st_csv_files = sorted(
                    path
                    for path in st_prefix.rglob("*.csv")
                    if "downloaded_at=" in _as_posix(path)
                )
                if not st_csv_files:
                    continue
                _load_target_files(
                    con, st_table, st_csv_files, sidecar_by_target, local_root, result
                )

    return result


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
        load_result = _load_ingest_tables(con, local_root, manifest_root)
        sidecar_rows = _load_sidecar_table(con, local_root)
        # telemetry_rows = _load_telemetry_table(con, local_root)
        # TODO: mimic the ingestion telemetry table load
        telemetry_rows = 0  # TODO: mimic the ingestion telemetry table load
        logger.info(
            "Loaded ingest_rows=%d sidecar_rows=%d telemetry_rows=%d",
            load_result.loaded_rows,
            sidecar_rows,
            telemetry_rows,
        )
        if load_result.failures:
            logger.error(
                "%d file(s) failed to load across %d target(s):",
                len(load_result.failures),
                len({f.table_name for f in load_result.failures}),
            )
            for failure in load_result.failures:
                logger.error(
                    "  %s / %s: %s",
                    failure.table_name,
                    failure.csv_path.name,
                    failure.error,
                )
        con.close()
        return 1 if load_result.failures else 0
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
