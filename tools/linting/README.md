# Linting Tools

This folder contains the canonical lint suite for the repository.

## Canonical Entry Point

- `./tools/linting/run_lint_suite.ps1`

This script is the single source of linting behavior used by:
- CI wrapper: `./tools/ci/ci_lint.ps1`
- Local wrapper: `./tools/local_dev/run_lint.ps1`
- pre-commit hook: `.pre-commit-config.yaml`

## Common Commands

Run lint checks:

```powershell
./tools/linting/run_lint_suite.ps1
```

Auto-fix and format:

```powershell
./tools/linting/run_lint_suite.ps1 -Fix
```

Install dev dependencies before linting:

```powershell
./tools/linting/run_lint_suite.ps1 -EnsureDeps
```

Run against specific targets:

```powershell
./tools/linting/run_lint_suite.ps1 function_app/src/run_ingestion.py tests/test_duckdb_revision_logic.py
```

Auto-fix specific targets:

```powershell
./tools/linting/run_lint_suite.ps1 -Fix function_app/src/run_ingestion.py
```

## Notes

- If no targets are provided, the suite runs on `.` (the whole repository).
- Keep lint logic changes in `run_lint_suite.ps1`; wrappers should remain thin.
