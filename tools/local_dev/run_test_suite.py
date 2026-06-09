from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path(__file__).resolve().with_name("test_suite_config.json")


@dataclass
class TestCaseResult:
    suite: str
    node: str
    status: str
    detail: str = ""


def _load_suite_config(config_path: Path) -> Dict[str, Dict[str, List[str]]]:
    if not config_path.exists():
        return {
            "python": {
                "include": ["tests/test_*.py"],
                "exclude": [
                    "tests/test_duckdb_*.py",
                    "tests/test_web_to_duckdb_e2e.py",
                ],
            },
            "duckdb": {
                "include": [
                    "tests/test_duckdb_*.py",
                    "tests/test_web_to_duckdb_e2e.py",
                ],
                "exclude": [],
            },
        }

    with config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    for key in ("python", "duckdb"):
        data.setdefault(key, {})
        data[key].setdefault("include", [])
        data[key].setdefault("exclude", [])
    return data


def _expand_patterns(
    include_patterns: Sequence[str], exclude_patterns: Sequence[str]
) -> List[str]:
    include_paths: List[Path] = []
    for pattern in include_patterns:
        include_paths.extend(REPO_ROOT.glob(pattern))

    exclude_set = {
        p.resolve() for pattern in exclude_patterns for p in REPO_ROOT.glob(pattern)
    }

    chosen = sorted(
        {p.resolve() for p in include_paths if p.resolve() not in exclude_set}
    )
    return [
        str(p.relative_to(REPO_ROOT)).replace("\\", "/") for p in chosen if p.is_file()
    ]


def _ensure_env_defaults(env: Dict[str, str]) -> None:
    env.setdefault("LOCAL_STORAGE_MODE", "true")
    env.setdefault("LOCAL_STORAGE_ROOT", str(REPO_ROOT / ".local_adls"))
    env.setdefault("MANIFEST_ROOT", str(REPO_ROOT / "tests" / "fixtures" / "manifests"))
    env.setdefault("MANUAL_INPUT_PREFIX", "manual")
    env.setdefault(
        "DUCKDB_FILE", str(REPO_ROOT / ".local_adls" / "suite_validation.duckdb")
    )


def _module_available(module_name: str) -> bool:
    probe = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return probe.returncode == 0


def _install_deps() -> int:
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-r",
        str(REPO_ROOT / "function_app" / "requirements.txt"),
        "-r",
        str(REPO_ROOT / "requirements-dev.txt"),
    ]
    return subprocess.call(cmd, cwd=REPO_ROOT)


def _parse_junit_xml(xml_path: Path, suite_name: str) -> List[TestCaseResult]:
    if not xml_path.exists():
        return []

    tree = ET.parse(xml_path)
    root = tree.getroot()

    cases: List[TestCaseResult] = []
    for tc in root.iter("testcase"):
        classname = tc.attrib.get("classname", "")
        name = tc.attrib.get("name", "")
        node = f"{classname}::{name}" if classname else name
        status = "passed"
        detail = ""

        failure = tc.find("failure")
        error = tc.find("error")
        skipped = tc.find("skipped")

        if failure is not None:
            status = "failed"
            detail = (failure.attrib.get("message") or "").strip()
        elif error is not None:
            status = "error"
            detail = (error.attrib.get("message") or "").strip()
        elif skipped is not None:
            status = "skipped"
            detail = (skipped.attrib.get("message") or "").strip()

        cases.append(
            TestCaseResult(suite=suite_name, node=node, status=status, detail=detail)
        )

    return cases


def _run_suite(
    suite_name: str,
    tests: Sequence[str],
    out_dir: Path,
    resume_last_failed: bool,
    extra_pytest_args: Sequence[str],
    env: Dict[str, str],
) -> tuple[int, List[TestCaseResult]]:
    xml_path = out_dir / f"{suite_name}.junit.xml"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-vv",
        "-rA",
        "--tb=short",
        f"--junitxml={xml_path}",
    ]

    if resume_last_failed:
        cmd.extend(["--lf", "--lfnf=all"])

    cmd.extend(extra_pytest_args)
    cmd.extend(tests)

    print(f"\n=== Running suite: {suite_name} ===")
    print("Command:", " ".join(cmd))
    rc = subprocess.call(cmd, cwd=REPO_ROOT, env=env)
    results = _parse_junit_xml(xml_path, suite_name)
    return rc, results


def _print_summary(
    results: Sequence[TestCaseResult], suite_exit_codes: Dict[str, int]
) -> int:
    passed = [r for r in results if r.status == "passed"]
    failed = [r for r in results if r.status == "failed"]
    errored = [r for r in results if r.status == "error"]
    skipped = [r for r in results if r.status == "skipped"]

    print("\n=== Test Suite Summary ===")
    for suite_name, code in suite_exit_codes.items():
        state = "PASS" if code == 0 else "FAIL"
        print(f"- {suite_name}: {state} (exit code {code})")

    passed_n, failed_n, errored_n, skipped_n = (
        len(passed),
        len(failed),
        len(errored),
        len(skipped),
    )
    print(
        f"\nTotals: passed={passed_n} failed={failed_n}"
        f" errors={errored_n} skipped={skipped_n}"
    )

    if passed:
        print("\nPassed tests:")
        for item in passed:
            print(f"- [{item.suite}] {item.node}")

    if failed or errored:
        print("\nFailed/Error tests:")
        for item in [*failed, *errored]:
            suffix = f" -> {item.detail}" if item.detail else ""
            print(f"- [{item.suite}] {item.node} ({item.status}){suffix}")

    if skipped:
        print("\nSkipped tests:")
        for item in skipped:
            print(f"- [{item.suite}] {item.node}")

    return (
        1
        if failed or errored or any(code != 0 for code in suite_exit_codes.values())
        else 0
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run unified local test suites (python + duckdb)."
    )
    parser.add_argument(
        "--suite",
        choices=["all", "python", "duckdb"],
        default="all",
        help="Which suite(s) to run. Default: all",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to suite config JSON with include/exclude globs.",
    )
    parser.add_argument(
        "--resume-last-failed",
        action="store_true",
        help="Resume from last failed tests where pytest cache is available.",
    )
    parser.add_argument(
        "--ensure-deps",
        action="store_true",
        help="Install requirements if pytest is missing before running suites.",
    )
    parser.add_argument(
        "--run-web-e2e",
        action="store_true",
        help="Enable web-backed e2e tests by setting RUN_WEB_E2E=true.",
    )
    parser.add_argument(
        "--run-integration",
        action="store_true",
        help="Enable live scraper integration tests by setting INTEGRATION_TESTS=1.",
    )
    parser.add_argument(
        "--extra-pytest-args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Additional args forwarded to pytest (after --).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.ensure_deps and not _module_available("pytest"):
        print("pytest not found. Installing dependencies...")
        if _install_deps() != 0:
            print("Dependency installation failed.")
            return 2

    if not _module_available("pytest"):
        print("pytest is not installed for this Python interpreter.")
        print("Run with --ensure-deps or install requirements-dev.txt.")
        return 2

    config = _load_suite_config(Path(args.config))

    suites_to_run: List[str]
    if args.suite == "all":
        suites_to_run = ["python", "duckdb"]
    else:
        suites_to_run = [args.suite]

    env = os.environ.copy()
    _ensure_env_defaults(env)
    if args.run_web_e2e:
        env["RUN_WEB_E2E"] = "true"
    if args.run_integration:
        env["INTEGRATION_TESTS"] = "1"

    out_dir = REPO_ROOT / ".pytest-suite-results"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results: List[TestCaseResult] = []
    suite_codes: Dict[str, int] = {}

    for suite in suites_to_run:
        include_patterns = config[suite]["include"]
        exclude_patterns = config[suite]["exclude"]
        tests = _expand_patterns(include_patterns, exclude_patterns)

        if not tests:
            print(f"No tests matched for suite '{suite}'.")
            suite_codes[suite] = 0
            continue

        rc, results = _run_suite(
            suite_name=suite,
            tests=tests,
            out_dir=out_dir,
            resume_last_failed=args.resume_last_failed,
            extra_pytest_args=args.extra_pytest_args,
            env=env,
        )
        suite_codes[suite] = rc
        all_results.extend(results)

    return _print_summary(all_results, suite_codes)


if __name__ == "__main__":
    raise SystemExit(main())
