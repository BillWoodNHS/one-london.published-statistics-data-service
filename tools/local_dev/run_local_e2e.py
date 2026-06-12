from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Add REPO_ROOT to sys.path for function_app imports
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from function_app.src.run_ingestion import execute_ingestion  # noqa: E402

LOCAL_ADLS = REPO_ROOT / ".local_adls"
FULL_MANIFEST_ROOT = REPO_ROOT / "config" / "datasets"
TEST_MANIFEST_ROOT = REPO_ROOT / "tests" / "fixtures" / "manifests"
DUCKDB_FILE = LOCAL_ADLS / "local_validation.duckdb"
DEFAULT_REPORT_DIR = LOCAL_ADLS / "reports"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run local end-to-end ingestion simulation with local storage emulation. "
            "By default, iterates through all manifests in MANIFEST_ROOT, "
            "executes ingestion for each, and verifies local artifacts. "
            "Use --pytest-only to run pytest test suite instead."
        )
    )
    parser.add_argument(
        "--pytest-only",
        action="store_true",
        help="Skip ingestion; only run pytest test suite.",
    )
    parser.add_argument(
        "--use-fixtures",
        action="store_true",
        help="Use tests/fixtures/manifests for pytest (implies --pytest-only).",
    )
    parser.add_argument(
        "--execution-mode",
        choices=["full", "scrape-only", "load-only"],
        default="full",
        help="INGEST_EXECUTION_MODE for function app runs during tests.",
    )
    parser.add_argument(
        "--dataset-profile-file",
        default="",
        help=(
            "Optional profile file path with INCLUDE_DATASET_IDS/"
            "EXCLUDE_DATASET_IDS entries."
        ),
    )
    parser.add_argument(
        "--max-files-per-dataset",
        type=int,
        default=0,
        help="LOCAL_MAX_FILES_PER_DATASET limit (0 disables limit).",
    )
    parser.add_argument(
        "--max-files-per-target",
        type=int,
        default=0,
        help="LOCAL_MAX_FILES_PER_TARGET limit (0 disables limit).",
    )
    parser.add_argument(
        "--max-total-files",
        type=int,
        default=0,
        help="LOCAL_MAX_TOTAL_FILES limit (0 disables limit).",
    )
    parser.add_argument(
        "--skip-verification",
        action="store_true",
        help="Skip post-run local verification and summary report generation.",
    )
    parser.add_argument(
        "--verification-report-dir",
        default="",
        help=(
            "Directory where verification json/markdown reports are written. "
            "Defaults to .local_adls/reports."
        ),
    )
    parser.add_argument(
        "--verification-report-prefix",
        default="local_run_summary",
        help="Filename prefix used for verification report artifacts.",
    )
    return parser.parse_args()


def _set_local_env(args: argparse.Namespace) -> None:
    os.environ["LOCAL_STORAGE_MODE"] = "true"
    os.environ["LOCAL_STORAGE_ROOT"] = str(LOCAL_ADLS)
    manifest_root = TEST_MANIFEST_ROOT if args.use_fixtures else FULL_MANIFEST_ROOT
    os.environ["MANIFEST_ROOT"] = str(manifest_root)
    os.environ.setdefault("MANUAL_INPUT_PREFIX", "manual")
    os.environ.setdefault("RUN_WEB_E2E", "true")
    os.environ.setdefault("DUCKDB_FILE", str(DUCKDB_FILE))
    os.environ["INGEST_EXECUTION_MODE"] = args.execution_mode

    if args.dataset_profile_file:
        os.environ["LOCAL_DATASET_PROFILE_FILE"] = args.dataset_profile_file

    os.environ["LOCAL_MAX_FILES_PER_DATASET"] = str(max(0, args.max_files_per_dataset))
    os.environ["LOCAL_MAX_FILES_PER_TARGET"] = str(max(0, args.max_files_per_target))
    os.environ["LOCAL_MAX_TOTAL_FILES"] = str(max(0, args.max_total_files))


def _run_pytest() -> int:
    return subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=REPO_ROOT)


def _run_ingestion() -> int:
    """Execute ingestion for all manifests in MANIFEST_ROOT.

    The execute_ingestion() function loads and processes all manifests
    from MANIFEST_ROOT internally, applying all configured filters and caps.

    Returns:
        0 on success, non-zero on failure.
    """
    try:
        result = execute_ingestion()
        if result.get("uploaded"):
            print("✓ Ingestion completed successfully")
            return 0
        else:
            print("⚠ Ingestion completed but no files were uploaded")
            return 0
    except Exception as e:
        print(f"✗ Error during ingestion: {e}")
        return 1


def _run_verification(args: argparse.Namespace) -> int:
    report_dir = (
        args.verification_report_dir
        or os.environ.get("LOCAL_VERIFY_REPORT_DIR", "")
        or str(DEFAULT_REPORT_DIR)
    )
    report_prefix = (
        args.verification_report_prefix
        or os.environ.get("LOCAL_VERIFY_REPORT_PREFIX", "")
        or "local_run_summary"
    )
    command = [
        sys.executable,
        "tools/local_dev/verify_local_run.py",
        "--local-root",
        str(LOCAL_ADLS),
        "--duckdb-file",
        os.environ["DUCKDB_FILE"],
        "--report-dir",
        report_dir,
        "--report-prefix",
        report_prefix,
    ]
    return subprocess.call(command, cwd=REPO_ROOT)


def main() -> int:
    args = _parse_args()

    # --use-fixtures implies --pytest-only
    if args.use_fixtures:
        args.pytest_only = True

    _set_local_env(args)

    if LOCAL_ADLS.exists():
        shutil.rmtree(LOCAL_ADLS)
    LOCAL_ADLS.mkdir(parents=True, exist_ok=True)

    print(f"Local storage path: {LOCAL_ADLS}")
    print(f"Manifest root: {os.environ['MANIFEST_ROOT']}")
    print(f"DuckDB file: {os.environ['DUCKDB_FILE']}")
    print(f"Execution mode: {os.environ['INGEST_EXECUTION_MODE']}")
    if os.environ.get("LOCAL_DATASET_PROFILE_FILE"):
        print(f"Dataset profile: {os.environ['LOCAL_DATASET_PROFILE_FILE']}")
    print(f"Max files per dataset: {os.environ['LOCAL_MAX_FILES_PER_DATASET']}")
    print(f"Max files per target: {os.environ['LOCAL_MAX_FILES_PER_TARGET']}")
    print(f"Max total files: {os.environ['LOCAL_MAX_TOTAL_FILES']}")

    # Choose execution mode
    if args.pytest_only:
        print("\nRunning pytest test suite only (ingestion skipped)...")
        code = _run_pytest()
    else:
        print("\nRunning direct ingestion simulation (full end-to-end)...")
        code = _run_ingestion()

    if code != 0:
        return code

    # Run verification unless skipped
    if not args.skip_verification:
        verify_code = _run_verification(args)
        if verify_code != 0:
            return verify_code

    mode_label = "pytest" if args.pytest_only else "ingestion"
    print(f"\nLocal e2e {mode_label} run completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
