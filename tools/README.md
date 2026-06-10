# Tools

Helper scripts and utilities for the scraper-driven dataset acquisition system.

## Directory Structure

```
tools/
├── scrape_config_builder/        # Helper tools for v2 JSON scrape-config generation
│   ├── scrape-config-helper.py
│   ├── generate-helper-input-from-csv.py
│   ├── promote-generated-configs.py
│   ├── promote-generated-configs.ps1
│   ├── README.md
│   └── helper_input/
│       └── appointments-in-general-practice.json
├── ci/                           # CI/CD pipeline scripts (Azure Pipelines / GitHub Actions)
│   ├── ci_dbt_deploy.ps1
│   ├── ci_lint.ps1
│   ├── ci_render_profiles_yml.ps1
│   └── ci_test.ps1
├── local_dev/                    # Local development utilities
│   ├── init_dev_environment.ps1
│   ├── run_local_e2e.ps1
│   └── run_local_e2e.py
└── README.md                     # This file
```

## scrape_config_builder

Automatic YAML configuration generator for the scraper-driven ingestion system.

**Purpose:** Infer scraper patterns (link selectors, text filters, file extensions, subject periods) from per-dataset JSON helper specs. Generate candidate YAML configs and validate discovery against live pages (non-download).

**Key Outputs:**
- Generated YAML configs under `tools/scrape_config_builder/helper_generated/<dataset_id>/run-<timestamp>/generated_configs/`
- Validation reports under `tools/scrape_config_builder/helper_generated/<dataset_id>/run-<timestamp>/reports/`
- Stable mirror under `tools/scrape_config_builder/helper_generated/<dataset_id>/latest/`
- Promotion script to copy generated YAML into `config/datasets`

Generated YAML includes a prioritized `subject_period.rules` block for runtime extraction:
1. `file_name`
2. `url_segment`
3. `page_text`

**Quick Start (from repo root):**
```powershell
# JSON mode (recommended)
python tools/scrape_config_builder/scrape-config-helper.py \
  --input-json tools/scrape_config_builder/helper_input/appointments-in-general-practice.json

# Promote latest generated YAML for one dataset
python tools/scrape_config_builder/promote-generated-configs.py \
  --dataset appointments-in-general-practice

# Promote latest generated YAML for one dataset (PowerShell wrapper)
./tools/scrape_config_builder/promote-generated-configs.ps1 \
  -Dataset appointments-in-general-practice

# CSV to v2 helper-input generation
python tools/scrape_config_builder/generate-helper-input-from-csv.py \
  --inventory psds-file-inventory.csv \
  --dataset appointments-in-general-practice
```

See [scrape_config_builder/README.md](scrape_config_builder/README.md) for:
- Full input modes documentation (JSON v0.1/v2.0 + CSV converter)
- JSON schema and field definitions
- Explicit Snowflake naming via `targets[].object_name_suffix`
- Subject period and publication date inference behavior
- Migration path from CSV inventory to JSON v2 helper inputs

### Input Modes

- **JSON v2 (required by helper):** `--input-json path/to/spec.json` or `--input-json-dir path/to/specs/`
- **CSV conversion (separate tool):** `python tools/scrape_config_builder/generate-helper-input-from-csv.py --inventory psds-file-inventory.csv`

## ci (CI/CD Scripts)

Azure Pipelines and GitHub Actions helper scripts.

- `ci_dbt_deploy.ps1` — Deploy dbt macros and models, render `profiles.yml`, run tests
- `ci_lint.ps1` — Run pre-commit linting (Ruff, etc.)
- `ci_render_profiles_yml.ps1` — Render secure `profiles.yml` from templates (key-pair or password auth)
- `ci_test.ps1` — Run test suites (Pytest, etc.)

**Configuration:**
Set these environment variables in CI/CD (see `docs/CI-CD.md`):
- `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_ROLE`, `SNOWFLAKE_DATABASE`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_SCHEMA`
- `SNOWFLAKE_PRIVATE_KEY` (recommended) + optional `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE`
- Or `SNOWFLAKE_PASSWORD` as fallback

Credentials are never stored in repo; `profiles.yml` is generated at runtime and cleaned up after use.

**Usage in Pipelines:**
```yaml
- script: |
    powershell -File tools/ci/ci_lint.ps1
  displayName: 'Run lint checks'

- script: |
    powershell -File tools/ci/ci_test.ps1
  displayName: 'Run tests'

- script: |
    powershell -File tools/ci/ci_dbt_deploy.ps1
  displayName: 'Deploy dbt models'
```

## local_dev (Local Development)

Local development utilities.

- `init_dev_environment.ps1` — Initialize Python virtual environment, install dependencies
- `run_local_e2e.ps1` — Run local end-to-end tests (PowerShell wrapper)
- `run_local_e2e.py` — Python implementation of local E2E tests

**Usage:**
```powershell
# Initialize environment
./tools/local_dev/init_dev_environment.ps1

# Recreate environment
./tools/local_dev/init_dev_environment.ps1 -RecreateVenv

# Run E2E tests
./tools/local_dev/run_local_e2e.ps1
```

## Common Workflows

### Build Scrape Configs

```powershell
# Single dataset from JSON
python tools/scrape_config_builder/scrape-config-helper.py \
  --input-json tools/scrape_config_builder/helper_input/appointments-in-general-practice.json

# Multiple datasets from JSON directory
python tools/scrape_config_builder/scrape-config-helper.py \
  --input-json-dir tools/scrape_config_builder/helper_input

# Validate + generate + summarize for a single dataset
./tools/scrape_config_builder/run-helper.ps1 \
  -InputJson tools/scrape_config_builder/helper_input/appointments-in-general-practice.json

# Promote latest generated config(s) into config/datasets
python tools/scrape_config_builder/promote-generated-configs.py \
  --dataset appointments-in-general-practice

# Promote latest generated config(s) into config/datasets (PowerShell wrapper)
./tools/scrape_config_builder/promote-generated-configs.ps1 \
  -Dataset appointments-in-general-practice

# CSV to helper-input v2 generation
python tools/scrape_config_builder/generate-helper-input-from-csv.py \
  --inventory psds-file-inventory.csv \
  --output-dir tools/scrape_config_builder/helper_input
```

### Local Development Setup

```powershell
# Initialize
./tools/local_dev/init_dev_environment.ps1

# Run E2E tests with local storage
./tools/local_dev/run_local_e2e.ps1
```

## Implementation Notes

- The scrape config builder does **not download files**; it validates discovery patterns only via HTTP fetch and regex matching.
- Publication dates and subject periods are **inferred** from page metadata and link text and can be improved via JSON v2 hints and samples.
- Helper JSON can optionally specify `targets[].object_name_suffix`; if omitted, the helper infers a default suffix from `dataset_id` and `sub_dataset_id`.
- Promoted YAML manifests should keep `object_name_suffix` explicit so Snowflake object names are stable and reviewable in source control.
- Generated YAML configs are **candidates** requiring manual review and testing before version control commit.
- CSV inputs are handled by `generate-helper-input-from-csv.py`; the main helper accepts JSON v2 only.
- All scripts support idempotent execution where practical.

## June 2026 Contract Update

- Storage paths now partition by download time (`download_year`, `download_month`, `downloaded_at`) rather than `subject_period`.
- Sidecar metadata now stores `_SUBJECT_PERIOD_FROM` and `_SUBJECT_PERIOD_TO` (inclusive timestamps) plus inference diagnostics.
- Target configs may include optional `period_coverage` hints to prioritize runtime period inference.
