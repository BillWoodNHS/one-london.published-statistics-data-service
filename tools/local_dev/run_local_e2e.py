from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Add REPO_ROOT to sys.path for function_app imports
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml  # noqa: E402

from function_app.src.run_ingestion import (  # noqa: E402
    _dataset_filter_sets,
    execute_ingestion,
)

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
        "--skip-duckdb-load",
        action="store_true",
        help=(
            "Skip loading local artifacts to DuckDB and skip dbt execution "
            "(ingestion-only run)."
        ),
    )
    parser.add_argument(
        "--skip-dbt-run",
        action="store_true",
        help=(
            "Skip dbt provisioning/model execution after local artifacts are "
            "loaded to DuckDB."
        ),
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
        "--schema-root",
        default=str(REPO_ROOT / "config" / "schemas"),
        help=(
            "Directory of known-schema YAML files (one per dataset_id), used "
            "for local-only schema drift warnings (default: config/schemas)."
        ),
    )
    parser.add_argument(
        "--schema-drift-threshold",
        type=float,
        default=0.20,
        help="Jaccard distance above which schema drift is reported (default: 0.20).",
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


def _dbt_command(*args: str) -> list[str]:
    # return [sys.executable, "-m", "dbt.cli.main", *args]
    return ["dbt", *args]


def _dbt_available() -> bool:
    result = subprocess.run(
        _dbt_command("--version"),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _run_dbt_local() -> int:
    if not _dbt_available():
        print("✗ dbt is not available in this Python environment.")
        print("  Install dbt-duckdb in your selected interpreter and retry.")
        return 1

    project_dir = str(REPO_ROOT / "dbt")
    profiles_dir = str(REPO_ROOT / "tests" / "fixtures" / "dbt")
    manifest_root = Path(os.environ["MANIFEST_ROOT"])
    manifests = sorted(
        list(manifest_root.glob("*.yml")) + list(manifest_root.glob("*.yaml"))
    )

    include_ids, exclude_ids = _dataset_filter_sets()
    if include_ids or exclude_ids:
        filtered_manifests = []
        for manifest_path in manifests:
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            dataset_id = raw.get("dataset_id", "")
            if include_ids and dataset_id not in include_ids:
                continue
            if dataset_id in exclude_ids:
                continue
            filtered_manifests.append(manifest_path)
        print(
            f"Dataset filter applied to dbt provisioning: "
            f"include={sorted(include_ids)} exclude={sorted(exclude_ids)} "
            f"selected={len(filtered_manifests)}/{len(manifests)}"
        )
        manifests = filtered_manifests

    print("\nRunning dbt deps...")
    deps_code = subprocess.call(
        _dbt_command(
            "deps",
            "--target",
            "test",
            "--project-dir",
            project_dir,
            "--profiles-dir",
            profiles_dir,
        ),
        cwd=REPO_ROOT,
    )
    if deps_code != 0:
        return deps_code

    print("\nProvisioning sidecar and telemetry pipelines...")
    for operation in ("provision_sidecar_pipeline", "provision_telemetry_pipeline"):
        code = subprocess.call(
            _dbt_command(
                "run-operation",
                operation,
                "--target",
                "test",
                "--args",
                "{}",
                "--project-dir",
                project_dir,
                "--profiles-dir",
                profiles_dir,
            ),
            cwd=REPO_ROOT,
        )
        if code != 0:
            return code

    print(f"\nProvisioning dataset objects for {len(manifests)} manifest(s)...")
    for manifest_path in manifests:
        args_json = json.dumps({"manifest_path": str(manifest_path)})
        for operation in (
            "provision_series_from_manifest",
            "provision_presentation_from_manifest",
        ):
            code = subprocess.call(
                _dbt_command(
                    "run-operation",
                    operation,
                    "--target",
                    "test",
                    "--args",
                    args_json,
                    "--project-dir",
                    project_dir,
                    "--profiles-dir",
                    profiles_dir,
                ),
                cwd=REPO_ROOT,
            )
            if code != 0:
                return code

    print("\nRunning dbt telemetry models...")
    return subprocess.call(
        _dbt_command(
            "run",
            "--target",
            "test",
            "--select",
            "telemetry",
            "--project-dir",
            project_dir,
            "--profiles-dir",
            profiles_dir,
        ),
        cwd=REPO_ROOT,
    )


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


def _load_local_artifacts_to_duckdb(args: argparse.Namespace) -> int:
    """Load downloaded artifacts into dbt-compatible ingest DuckDB tables.

    Returns:
        0 on success (or duckdb not available), non-zero on failure.
    """
    command = [
        sys.executable,
        "tools/local_dev/load_csvs_to_duckdb.py",
        "--local-root",
        str(LOCAL_ADLS),
        "--manifest-root",
        os.environ["MANIFEST_ROOT"],
        "--duckdb-file",
        os.environ["DUCKDB_FILE"],
        "--schema-root",
        args.schema_root,
        "--schema-drift-threshold",
        str(args.schema_drift_threshold),
    ]
    return subprocess.call(command, cwd=REPO_ROOT)


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
    print(f"Schema root: {args.schema_root}")
    print(f"Schema drift threshold: {args.schema_drift_threshold}")

    # Choose execution mode
    load_had_failures = False
    if args.pytest_only:
        print("\nRunning pytest test suite only (ingestion skipped)...")
        code = _run_pytest()
    else:
        print("\nRunning direct ingestion simulation (full end-to-end)...")
        code = _run_ingestion()
        if code == 0 and not args.skip_duckdb_load:
            print("\nLoading local artifacts to DuckDB ingest tables...")
            load_code = _load_local_artifacts_to_duckdb(args)
            if load_code != 0:
                # The loader isolates failures per file/target and already
                # attempted every dataset, so a non-zero exit here means
                # "some files failed" rather than "nothing was loaded" -
                # continue to dbt for the datasets that did load, but still
                # surface the failure in the final exit code.
                print("⚠ DuckDB artifact load completed with failures (see log above).")
                load_had_failures = True
            if not args.skip_dbt_run:
                print("\nRunning dbt provisioning and telemetry models...")
                dbt_code = _run_dbt_local()
                if dbt_code != 0:
                    print("✗ dbt execution failed.")
                    return dbt_code
        elif args.skip_duckdb_load:
            print("\nSkipping DuckDB artifact load and dbt execution.")

    if code != 0:
        return code

    # Run verification unless skipped
    if not args.skip_verification:
        verify_code = _run_verification(args)
        if verify_code != 0:
            return verify_code

    mode_label = "pytest" if args.pytest_only else "ingestion"
    if load_had_failures:
        print(f"\nLocal e2e {mode_label} run completed with DuckDB load failures.")
        return 1

    print(f"\nLocal e2e {mode_label} run completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
