from __future__ import annotations

import argparse
import datetime
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect local ingestion artifacts and emit verification reports."
    )
    parser.add_argument(
        "--local-root",
        default="",
        help="Local storage root. Defaults to LOCAL_STORAGE_ROOT or .local_adls.",
    )
    parser.add_argument(
        "--duckdb-file",
        default="",
        help=(
            "DuckDB file path. Defaults to DUCKDB_FILE or "
            "<local-root>/local_validation.duckdb."
        ),
    )
    parser.add_argument(
        "--report-dir",
        default="",
        help="Optional output directory for json/markdown summary reports.",
    )
    parser.add_argument(
        "--report-prefix",
        default="local_run_summary",
        help="Prefix used for report filenames.",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Print JSON report payload to stdout.",
    )
    return parser.parse_args()


def _resolve_local_root(raw: str) -> Path:
    if raw:
        return Path(raw).resolve()
    from_env = Path(Path.cwd() / ".local_adls")
    import os

    configured = os.environ.get("LOCAL_STORAGE_ROOT", "")
    if configured:
        return Path(configured).resolve()
    return from_env.resolve()


def _resolve_duckdb_path(raw: str, local_root: Path) -> Path:
    if raw:
        return Path(raw).resolve()
    import os

    configured = os.environ.get("DUCKDB_FILE", "")
    if configured:
        return Path(configured).resolve()
    return (local_root / "local_validation.duckdb").resolve()


def _collect_csv_files(local_root: Path) -> List[Path]:
    if not local_root.exists():
        return []
    return sorted(path for path in local_root.rglob("*.csv") if path.is_file())


def _collect_sidecars(local_root: Path) -> List[Path]:
    if not local_root.exists():
        return []
    return sorted(
        path for path in local_root.rglob("_INGEST_METADATA.json") if path.is_file()
    )


def _series_subdataset_from_path(local_root: Path, csv_path: Path) -> Tuple[str, str]:
    try:
        rel = csv_path.relative_to(local_root)
        parts = rel.parts
        if len(parts) >= 2:
            return parts[0], parts[1]
    except Exception:
        pass
    return "unknown", "unknown"


def _load_sidecar(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _duckdb_table_summary(duckdb_path: Path) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "duckdb_available": False,
        "database_exists": duckdb_path.exists(),
        "path": str(duckdb_path),
        "table_count": 0,
        "tables": [],
    }
    if not duckdb_path.exists():
        return summary

    try:
        import duckdb  # type: ignore
    except Exception:
        return summary

    summary["duckdb_available"] = True
    con = duckdb.connect(str(duckdb_path))
    try:
        rows = con.execute(
            """
            select table_name, table_type
            from information_schema.tables
            where table_schema = 'main'
            order by table_name
            """
        ).fetchall()

        tables: List[Dict[str, Any]] = []
        for table_name, table_type in rows:
            row_count: Optional[int] = None
            try:
                row_count = int(
                    con.execute(f'select count(*) from "{table_name}"').fetchone()[0]
                )
            except Exception:
                row_count = None

            column_count = len(
                con.execute(f"PRAGMA table_info('{table_name}')").fetchall()
            )
            tables.append(
                {
                    "name": table_name,
                    "type": table_type,
                    "row_count": row_count,
                    "column_count": column_count,
                }
            )

        summary["tables"] = tables
        summary["table_count"] = len(tables)
        return summary
    finally:
        con.close()


def _build_report(local_root: Path, duckdb_path: Path) -> Dict[str, Any]:
    csv_files = _collect_csv_files(local_root)
    sidecars = _collect_sidecars(local_root)

    file_counts: Dict[Tuple[str, str], int] = defaultdict(int)
    for csv_file in csv_files:
        key = _series_subdataset_from_path(local_root, csv_file)
        file_counts[key] += 1

    sidecar_records = [_load_sidecar(path) for path in sidecars]
    sidecar_by_source = {
        str(record.get("_SOURCE_FILE_PATH", ""))
        for record in sidecar_records
        if record.get("_SOURCE_FILE_PATH")
    }

    csv_sources = set(str(path) for path in csv_files)

    report: Dict[str, Any] = {
        "generated_at_utc": datetime.datetime.now(datetime.UTC).isoformat(
            timespec="seconds"
        )
        + "Z",
        "local_root": str(local_root),
        "csv_file_count": len(csv_files),
        "sidecar_file_count": len(sidecars),
        "files_by_series_sub_dataset": [
            {
                "series_id": series_id,
                "sub_dataset_id": sub_dataset_id,
                "csv_file_count": count,
            }
            for (series_id, sub_dataset_id), count in sorted(file_counts.items())
        ],
        "sidecar_source_url_count": len(sidecar_by_source),
        "csv_path_sample": [str(path) for path in csv_files[:25]],
        "duckdb": _duckdb_table_summary(duckdb_path),
        "observations": {
            "csv_without_sidecar_possible": len(csv_files) > len(sidecars),
            "sidecar_without_csv_possible": len(sidecars) > len(csv_files),
            "csv_file_path_count": len(csv_sources),
        },
    }
    return report


def _to_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Local Run Verification Summary",
        "",
        f"- Generated (UTC): {report['generated_at_utc']}",
        f"- Local root: {report['local_root']}",
        f"- CSV files: {report['csv_file_count']}",
        f"- Sidecar files: {report['sidecar_file_count']}",
        f"- Sidecar source URL count: {report['sidecar_source_url_count']}",
        "",
        "## Files by Series and Sub-dataset",
        "",
        "| Series ID | Sub-dataset ID | CSV Files |",
        "|---|---|---:|",
    ]

    for row in report["files_by_series_sub_dataset"]:
        lines.append(
            "| {series_id} | {sub_dataset_id} | {csv_file_count} |".format(**row)
        )

    duckdb = report["duckdb"]
    lines.extend(
        [
            "",
            "## DuckDB",
            "",
            f"- Database path: {duckdb['path']}",
            f"- Database exists: {duckdb['database_exists']}",
            f"- DuckDB import available: {duckdb['duckdb_available']}",
            f"- Tables found: {duckdb['table_count']}",
            "",
            "| Table | Type | Rows | Columns |",
            "|---|---|---:|---:|",
        ]
    )

    for table in duckdb["tables"]:
        row_value = table["row_count"]
        lines.append(
            f"| {table['name']} | {table['type']} | "
            f"{row_value if row_value is not None else 'n/a'} | "
            f"{table['column_count']} |"
        )

    return "\n".join(lines) + "\n"


def _write_reports(
    report: Dict[str, Any], report_dir: Path, report_prefix: str
) -> Tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{report_prefix}.json"
    md_path = report_dir / f"{report_prefix}.md"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(_to_markdown(report), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    args = _parse_args()
    local_root = _resolve_local_root(args.local_root)
    duckdb_path = _resolve_duckdb_path(args.duckdb_file, local_root)
    report = _build_report(local_root, duckdb_path)

    print("Local verification summary")
    print(f"  Local root: {local_root}")
    print(f"  CSV files: {report['csv_file_count']}")
    print(f"  Sidecar files: {report['sidecar_file_count']}")
    print(f"  DuckDB tables: {report['duckdb']['table_count']}")

    if args.report_dir:
        json_path, md_path = _write_reports(
            report,
            Path(args.report_dir).resolve(),
            args.report_prefix,
        )
        print(f"  JSON report: {json_path}")
        print(f"  Markdown report: {md_path}")

    if args.print_json:
        json.dump(report, sys.stdout, indent=2)
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
