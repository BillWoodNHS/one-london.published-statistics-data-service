# Copilot Instructions for This Repository

These instructions apply to all Copilot-generated edits in this repository.

## Python and Ruff requirements

- Keep all Python code compatible with Ruff configuration in `pyproject.toml`.
- Respect line length limit `88` and avoid introducing long string or SQL fixture lines.
- Prefer multiline wrapping over disabling lint rules.
- Keep imports sorted and grouped so Ruff import checks pass.

## Preferred editing behavior

- When creating or editing Python files, proactively format long dict literals, function calls, and test fixture rows across multiple lines.
- For long SQL in test strings, split `VALUES` rows and conditions across lines to keep each line <= 88 chars.
- Do not add `# noqa` unless explicitly requested.

## Validation before finalizing

Run local lint checks after significant edits:

```powershell
./tools/linting/run_lint_suite.ps1
```

If fixes are needed, use:

```powershell
./tools/linting/run_lint_suite.ps1 -Fix
```

## Scope reminder

- Prefer minimal, targeted changes.
- Do not reformat unrelated files.