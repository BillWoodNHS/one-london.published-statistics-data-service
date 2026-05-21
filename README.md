# One London Published Statistics Data Service

This repository provides a manifest-driven data ingestion and validation service for published statistics.

It is designed to:
- discover downloadable files from supplier publication pages,
- land normalized CSV data into ADLS-compatible paths,
- preserve ingestion metadata,
- support manual fallback acquisition,
- provision Snowflake ingestion objects via dbt macros,
- validate core transformation behavior locally with DuckDB.

## Project Structure

- `config/`: Dataset and supplier configuration manifests.
- `function_app/`: Azure Functions ingestion runtime.
- `dbt/`: dbt project and macros for aliasing, revision views, and provisioning.
- `tests/`: Unit and integration tests (including web-backed tests).
- `tools/`: Local developer and test runner scripts.

See folder-level README files for details.

## Prerequisites

- Python 3.11+
- PowerShell 7+ (recommended on Windows)
- Internet access for web-backed integration tests

## Quick Start

1. Initialize local developer environment:

```powershell
./tools/init_dev_environment.ps1
```

2. Run the full test suite:

```powershell
python -m pytest -q
```

3. Run full suite including web-backed tests:

```powershell
$env:RUN_WEB_E2E = 'true'
python -m pytest -q
Remove-Item Env:RUN_WEB_E2E -ErrorAction SilentlyContinue
```

## Local End-to-End Run

Use the local orchestration script:

```powershell
./tools/run_local_e2e.ps1
```

This sets local storage emulation and runs pytest using fixture manifests.

## Ingestion Runtime Configuration

Primary environment variables:
- `MANIFEST_ROOT`: path to manifest files (default `../config/datasets` from function app).
- `LOCAL_STORAGE_MODE`: `true` to use local filesystem instead of Azure Blob.
- `LOCAL_STORAGE_ROOT`: local root path when `LOCAL_STORAGE_MODE=true`.
- `MANUAL_INPUT_PREFIX`: ADLS/manual prefix for fallback files.
- `ADLS_ACCOUNT_URL`, `ADLS_CONTAINER`, `ADLS_PREFIX`: production storage settings.

Sample local settings are provided at `function_app/local.settings.sample.json`.

## Adding a New Dataset Configuration

1. Create a new YAML file in `config/datasets/`.
2. Define required top-level keys:
   - `dataset_id`
   - `series_id`
   - `entry_url`
   - `publication_date` with `source` and `pattern`
   - `targets` (one or more)
   - optional `subject_period` with `source` and `pattern`
3. For each target, define:
   - `sub_dataset_id`
   - `scrape_steps` with `link_selector` and optional `text_filter`, `file_extensions`
   - optional `page_date_selectors` for page-level publication/revision extraction
   - optional `reporting_period_columns`
4. Optionally define `fallback` settings for manual acquisition.
5. Add tests or extend fixture coverage under `tests/`.
6. Run `python -m pytest -q` and, where relevant, web-backed tests.

Example manifests are available under `config/datasets/` and `tests/fixtures/manifests/`.

## dbt and Snowflake Provisioning Notes

The dbt project includes macros to:
- normalize column names to SCREAMING_SNAKE_CASE,
- generate presentation and revision views,
- create storage integration, file format, raw tables, stages, and pipes.

Before using dbt operations, ensure dependencies are installed:

```powershell
dbt deps --project-dir ./dbt
```


## CI/CD Pipeline & Secure Deployment

This project supports robust, secure, and environment-agnostic CI/CD for dbt/Snowflake deployments using both GitHub Actions and Azure DevOps. All pipeline logic is implemented in reusable PowerShell scripts under `tools/`.

- **Linting**: Runs pre-commit checks (ruff check + ruff format) on all branches.
- **Testing**: Runs the full pytest suite (unit and integration) on all branches.
- **Deployment**: Runs `dbt run` and `dbt test` against Snowflake on the `main` branch only.

See [docs/CI-CD.md](docs/CI-CD.md) for full details, including:
- Required secrets/variables for both platforms
- How to use key-pair authentication for Snowflake (recommended)
- How credentials are handled securely
- How to test deployment scripts locally

### Quick Reference: Secure Snowflake Auth

- Set `SNOWFLAKE_PRIVATE_KEY` (and optional `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE`) for key-pair auth
- If not set, falls back to `SNOWFLAKE_PASSWORD`
- The script `tools/ci_render_profiles_yml.ps1` generates a secure `profiles.yml` for dbt at runtime

## Quality Gates

Recommended checks before commit:
- `python -m pre_commit run --all-files`
- `python -m pytest -q`
- `RUN_WEB_E2E=true python -m pytest -q tests/test_web_to_duckdb_e2e.py`
