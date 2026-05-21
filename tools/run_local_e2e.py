from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_ADLS = REPO_ROOT / ".local_adls"
TEST_MANIFEST_ROOT = REPO_ROOT / "tests" / "fixtures" / "manifests"
DUCKDB_FILE = LOCAL_ADLS / "local_validation.duckdb"


def _set_local_env() -> None:
    os.environ["LOCAL_STORAGE_MODE"] = "true"
    os.environ["LOCAL_STORAGE_ROOT"] = str(LOCAL_ADLS)
    os.environ.setdefault("MANIFEST_ROOT", str(TEST_MANIFEST_ROOT))
    os.environ.setdefault("MANUAL_INPUT_PREFIX", "manual")
    os.environ.setdefault("RUN_WEB_E2E", "true")
    os.environ.setdefault("DUCKDB_FILE", str(DUCKDB_FILE))


def _run_pytest() -> int:
    return subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=REPO_ROOT)


def main() -> int:
    _set_local_env()

    if LOCAL_ADLS.exists():
        shutil.rmtree(LOCAL_ADLS)
    LOCAL_ADLS.mkdir(parents=True, exist_ok=True)
    print(f"Local storage path: {LOCAL_ADLS}")
    print(f"Manifest root: {os.environ['MANIFEST_ROOT']}")
    print(f"DuckDB file: {os.environ['DUCKDB_FILE']}")

    code = _run_pytest()
    if code != 0:
        return code

    print("Local e2e run completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
