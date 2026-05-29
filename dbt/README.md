# dbt Project

This folder contains the dbt project used for:
- Snowflake ingestion object provisioning (storage integration, stages, pipes, INGEST tables),
- Deduplication views (RAW schema) over INGEST tables,
- Presentation layer views with column aliasing and time-based filtering.

## Data Architecture: INGEST → RAW → PRESENTATION

The project implements a three-layer data pipeline with clear separation of concerns:

### INGEST Schema
- **Snowpipe target tables** receiving direct loads from Azure Blob Storage
- **Full audit trail** of all file uploads (including re-uploads and duplicates)
- **Auto-evolving schema** via Snowflake's `enable_schema_evolution=true`
- **Table naming**: `INGEST_{SERIES_TOKEN}_{SUB_DATASET_TOKEN}`
- **Metadata columns**: `_INGESTED_AT`, `_SOURCE_FILE_NAME`, `_FILE_CONTENT_KEY`, etc.
- **No maintenance required**: New columns in CSV files automatically detected and added

### RAW Schema
- **Deduplicated views** over INGEST tables — always reflect current data with zero lag
- **Window function deduplication** based on file content hash (`_FILE_CONTENT_KEY`)
- **Source of truth** for analytics (single copy per unique file upload)
- **Schema auto-inherits** from INGEST: new CSV columns flow through immediately via `SELECT * EXCLUDE`
- **Created by `create_raw_dedup_view` macro** — no per-dataset SQL files required
- **Upgrade path**: can be promoted to a Dynamic Table if query performance requires it

### PRESENTATION Schema
- **Business views** on top of RAW tables
- **Reporting period filtering** (e.g., latest publication date per dataset)
- **Column aliasing** for consumer-friendly names
- **Read-only** (no durability concerns)

## Contents

- `dbt_project.yml`: Project config and variables (including `ingest_schema`, `raw_schema`, `presentation_schema`)
- `packages.yml`: dbt package declarations
- `macros/`:
  - `ingestion/`: INGEST and RAW table provisioning, storage integration, stage/pipe setup
  - `telemetry/`: Function app event ingestion, quality profiling
  - `presentation/`: View creation, column aliasing
- `models/`:
  - `generated/`: Bootstrap scripts
  - `telemetry/`: Telemetry models and sources

## Setup

Install dependencies before running operations:

```powershell
dbt deps --project-dir ./dbt
```

## Important Variables

Defined in `dbt_project.yml` under `vars`, including:
- `ingest_schema`: INGEST (Snowpipe load targets)
- `raw_schema`: RAW (deduplicated source of truth)
- `presentation_schema`: PRESENTATION (business views)
- `infra_schema`: INFRA (storage integration, stages, file formats)
- `adls_url_root`: Azure Blob Storage root URL
- `storage_integration_name`: Snowflake storage integration name
- `file_format_name`: Snowflake CSV file format name
- `managed_identity_tenant_id`: Azure managed identity tenant
- `telemetry_prefix`: Prefix for telemetry events in ADLS
- `telemetry_file_format_name`: File format for telemetry JSON

## Creating New Dataset Pipelines

### 1. Create Dataset Manifest
Create `config/datasets/<dataset_id>.yml` with series and target configuration.

### 2. Provision Snowflake Objects
```powershell
dbt run-operation one_london_psds.provision_series_from_manifest \
  --args 'manifest_path: ../config/datasets/<dataset_id>.yml'
```

This creates in a single operation:
- `INGEST_<SERIES>_<DATASET>` table (receives Snowpipe loads, auto-evolving schema)
- `STG_<SERIES>_<DATASET>` Snowflake external stage
- `PIPE_<SERIES>_<DATASET>` Snowpipe pipe
- `RAW_<SERIES>_<DATASET>` table (deduplicated, inherits INGEST schema)

No SQL files per dataset are required — the macro applies identical logic to every dataset.

### 3. Create Presentation Views (Optional)
Add views in `models/generated/` that reference the RAW table.

### Refreshing RAW Tables

When new data has arrived in INGEST and you want to refresh all RAW tables for a series:

```powershell
dbt run-operation one_london_psds.provision_series_from_manifest \
  --args 'manifest_path: ../config/datasets/<dataset_id>.yml'
```

Re-running provisioning is safe and idempotent — INGEST tables and pipes use `IF NOT EXISTS`, while RAW tables use `CREATE OR REPLACE`.

## Deployment Settings File

Non-secret dbt/Snowflake deployment settings can be supplied via:
- `config/dbt/deployment.settings.json`

The CI deployment script (`tools/ci_dbt_deploy.ps1`) loads this file by default,
or from `DBT_DEPLOYMENT_SETTINGS_PATH` when provided. Secrets (account/user/password
or private key) still come from environment variables/secrets.

## Adding New Macro Behavior Safely

1. Update macro code in `macros/`.
2. Add or update tests that execute macro materialization via DuckDB/dbt harness.
3. Validate with pytest.

## Key Design Decisions

### Why Separate INGEST and RAW Layers?

| Aspect | INGEST | RAW |
|--------|--------|-----|
| **Role** | Audit trail | Source of truth |
| **Duplicates** | Preserved | Removed |
| **Schema** | Auto-evolves (Snowflake) | Inherits via `SELECT * EXCLUDE` |
| **Created by** | `create_ingest_table` macro | `create_raw_dedup_table` macro |
| **Refreshed by** | Snowpipe (automatic) | Re-running `provision_series_from_manifest` |
| **Re-uploads** | Visible as separate rows | Deduplicated to latest version |
| **Per-dataset SQL files** | None required | None required |

### Why `SELECT * EXCLUDE (_dedup_rank)` in the RAW macro?

This pattern ensures the macro:
- Automatically inherits new columns as CSV files add them
- Requires zero maintenance when schemas evolve
- Stays in sync with INGEST auto-evolution
- Preserves all metadata columns (`_FILE_CONTENT_KEY`, `_INGESTED_AT`, etc.)

