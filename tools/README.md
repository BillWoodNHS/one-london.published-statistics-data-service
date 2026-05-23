# Tools

Helper scripts and utilities for the scraper-driven dataset acquisition system.

## Directory Structure

```
tools/
├── scrape_config_builder/        # Helper tool for generating scraper configs from inventory
│   ├── build_scrape_configs_from_inventory.py
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

**Purpose:** Infer scraper patterns (link selectors, text filters, file extensions, subject periods) from CSV inventory or per-dataset JSON specs. Generate candidate YAML configs and validate discovery against live pages (non-download).

**Key Outputs:**
- Generated YAML configs (ready for manual review)
- `helper_suggestions.csv` (inferred selectors, patterns, extensions)
- `matches_found.csv` (live discovery validation with inferred subject periods and publication dates)
- `normalized_input_specs/*.json` (normalized input specs for CSV-to-JSON migration)

**Quick Start (from repo root):**
```powershell
# JSON mode (recommended)
python tools/scrape_config_builder/build_scrape_configs_from_inventory.py \
  --input-json tools/scrape_config_builder/helper_input/appointments-in-general-practice.json

# CSV mode (legacy, bulk seed)
python tools/scrape_config_builder/build_scrape_configs_from_inventory.py \
  --inventory psds-file-inventory.csv \
  --dataset appointments-in-general-practice
```

See [scrape_config_builder/README.md](scrape_config_builder/README.md) for:
- Full input modes documentation (CSV, JSON, mixed)
- JSON schema and field definitions
- Subject period and publication date inference behavior
- Migration path from CSV to JSON-first workflows

### Input Modes

- **JSON (recommended):** `--input-json path/to/spec.json` or `--input-json-dir path/to/specs/`
- **CSV (legacy):** `--inventory psds-file-inventory.csv`
- **Mixed:** Combine both; JSON specs override CSV defaults by dataset_id

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
python tools/scrape_config_builder/build_scrape_configs_from_inventory.py \
  --input-json tools/scrape_config_builder/helper_input/appointments-in-general-practice.json

# Multiple datasets from JSON directory
python tools/scrape_config_builder/build_scrape_configs_from_inventory.py \
  --input-json-dir tools/scrape_config_builder/helper_input

# CSV + JSON (mixed)
python tools/scrape_config_builder/build_scrape_configs_from_inventory.py \
  --inventory psds-file-inventory.csv \
  --input-json tools/scrape_config_builder/helper_input/appointments-in-general-practice.json
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
- Publication dates and subject periods are **inferred** from page metadata and link text; they can be overridden in JSON specs.
- Generated YAML configs are **candidates** requiring manual review and testing before version control commit.
- CSV inputs are backwards-compatible for bulk seeding; **JSON-first workflows are recommended** for new datasets.
- All scripts support idempotent execution where practical.
