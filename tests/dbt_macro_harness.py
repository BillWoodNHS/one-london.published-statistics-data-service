from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DBT_PROFILES_DIR = Path(__file__).resolve().parent / "fixtures" / "dbt"
DBT_PROJECT_DIR = REPO_ROOT / "dbt"
_DBT_DEPS_READY = False


def _dbt_available() -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "dbt.cli.main", "--version"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def require_dbt() -> None:
    if not _dbt_available():
        pytest.skip("dbt-duckdb is not installed in the current environment.")


def _ensure_dbt_deps(env: dict[str, str]) -> None:
    global _DBT_DEPS_READY
    if _DBT_DEPS_READY:
        return

    if not (DBT_PROJECT_DIR / "packages.yml").exists():
        _DBT_DEPS_READY = True
        return

    deps_command = [
        sys.executable,
        "-m",
        "dbt.cli.main",
        "deps",
        "--project-dir",
        str(DBT_PROJECT_DIR),
        "--profiles-dir",
        str(DBT_PROFILES_DIR),
        "--log-format",
        "json",
    ]
    deps_result = subprocess.run(
        deps_command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if deps_result.returncode != 0:
        raise AssertionError(
            "dbt deps failed before macro execution.\n"
            f"stdout:\n{deps_result.stdout}\n"
            f"stderr:\n{deps_result.stderr}"
        )
    _DBT_DEPS_READY = True


def render_alias_select_sql(column_names: list[str], duckdb_file: Path) -> str:
    require_dbt()

    env = os.environ.copy()
    env["DUCKDB_FILE"] = str(duckdb_file)
    duckdb_file.parent.mkdir(parents=True, exist_ok=True)
    _ensure_dbt_deps(env)

    args = json.dumps({"column_names": column_names})
    command = [
        sys.executable,
        "-m",
        "dbt.cli.main",
        "run-operation",
        "emit_alias_select_sql",
        "--args",
        args,
        "--project-dir",
        str(DBT_PROJECT_DIR),
        "--profiles-dir",
        str(DBT_PROFILES_DIR),
        "--log-format",
        "json",
    ]

    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    if result.returncode != 0:
        raise AssertionError(
            "dbt run-operation failed while rendering alias SQL.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    prefix = "__ALIAS_SELECT_SQL__"
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            if prefix in line:
                return line.split(prefix, 1)[1]
            continue

        message = str(event.get("info", {}).get("msg", ""))
        if prefix in message:
            return message.split(prefix, 1)[1]

    raise AssertionError(
        "Could not find emitted alias SQL in dbt output.\n"
        f"{result.stdout}\n{result.stderr}"
    )


def render_presentation_view_columns(
    raw_schema: str,
    raw_table: str,
    view_name: str,
    column_names: list[str],
    duckdb_file: Path,
) -> list[str]:
    require_dbt()

    env = os.environ.copy()
    env["DUCKDB_FILE"] = str(duckdb_file)
    duckdb_file.parent.mkdir(parents=True, exist_ok=True)
    _ensure_dbt_deps(env)

    args = json.dumps(
        {
            "raw_schema": raw_schema,
            "raw_table": raw_table,
            "view_name": view_name,
            "column_names": column_names,
        }
    )
    command = [
        sys.executable,
        "-m",
        "dbt.cli.main",
        "run-operation",
        "test_create_presentation_view_with_aliasing",
        "--args",
        args,
        "--project-dir",
        str(DBT_PROJECT_DIR),
        "--profiles-dir",
        str(DBT_PROFILES_DIR),
        "--log-format",
        "json",
    ]

    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    if result.returncode != 0:
        raise AssertionError(
            "dbt run-operation failed while rendering presentation view columns.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    prefix = "__PRESENTATION_VIEW_COLUMNS__"
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            if prefix in line:
                return line.split(prefix, 1)[1].split(",")
            continue

        message = str(event.get("info", {}).get("msg", ""))
        if prefix in message:
            return message.split(prefix, 1)[1].split(",")

    raise AssertionError(
        "Could not find emitted presentation view columns in dbt output.\n"
        f"{result.stdout}\n{result.stderr}"
    )
