"""Load downloaded CSVs from local ADLS into DuckDB for inspection."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

try:
    import duckdb
except ImportError:
    duckdb = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _get_csv_files(local_root: Path) -> list[Path]:
    """Find all CSV files in local ADLS, excluding sidecars and metadata."""
    csv_files = []
    for csv_path in local_root.rglob("*.csv"):
        # Skip sidecar/metadata files
        if csv_path.name.startswith("_"):
            continue
        # Only include files with downloaded_at partition marker
        if "downloaded_at=" not in csv_path.as_posix():
            continue
        csv_files.append(csv_path)
    return sorted(csv_files)


def _load_csvs(local_root: Path, duckdb_path: Path) -> int:
    """Load all CSVs from local_root into a DuckDB database."""
    if duckdb is None:
        logger.error("DuckDB not installed. Run: pip install duckdb")
        return 1

    csv_files = _get_csv_files(local_root)
    if not csv_files:
        logger.info("No CSV files found in %s", local_root)
        return 0

    logger.info("Found %d CSV files to load", len(csv_files))

    try:
        con = duckdb.connect(str(duckdb_path))
        loaded = 0

        for csv_path in csv_files:
            # Use relative path from series_id/sub_dataset_id for table naming
            parts = csv_path.relative_to(local_root).parts
            if len(parts) >= 2:
                series_id = parts[0]
                sub_dataset = parts[1] if len(parts) > 2 else "default"
                table_name = f"{series_id}_{sub_dataset}".replace("-", "_")
            else:
                table_name = csv_path.stem.replace("-", "_")

            # Sanitize table name
            table_name = "".join(
                c if c.isalnum() or c == "_" else "_" for c in table_name
            )

            try:
                # Load CSV, allow flexible schema
                con.execute(
                    f"""
                    CREATE OR REPLACE TABLE {table_name} AS
                    SELECT * FROM read_csv_auto(?, header=true, all_varchar=true)
                    """,
                    [str(csv_path)],
                )
                loaded += 1
                row_count = con.execute(
                    f"SELECT COUNT(*) FROM {table_name}"
                ).fetchone()[0]
                logger.info("  Loaded: %s (%s rows)", table_name, row_count)
            except Exception as e:
                logger.warning("  Failed to load %s: %s", csv_path.name, e)

        logger.info("Successfully loaded %d tables to %s", loaded, duckdb_path)
        con.close()
        return 0

    except Exception as e:
        logger.error("Error loading CSVs to DuckDB: %s", e)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load downloaded CSVs from local ADLS into DuckDB."
    )
    parser.add_argument(
        "--local-root",
        type=Path,
        default=Path(".") / ".local_adls",
        help="Local ADLS root directory (default: .local_adls)",
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

    duckdb_file = args.duckdb_file
    if not duckdb_file:
        duckdb_file = local_root / "local_validation.duckdb"

    logger.info("Loading CSVs from: %s", local_root)
    logger.info("DuckDB destination: %s", duckdb_file)

    return _load_csvs(local_root, duckdb_file)


if __name__ == "__main__":
    raise SystemExit(main())
