# dbt Project

This folder contains the dbt project used for:
- column aliasing rules,
- revision view generation,
- Snowflake ingestion object provisioning.

## Contents

- `dbt_project.yml`: Project config and variables.
- `packages.yml`: dbt package declarations.
- `macros/`: Reusable SQL/Jinja macros.
- `models/`: Project models.

## Setup

Install dependencies before running operations:

```powershell
dbt deps --project-dir ./dbt
```

## Important Variables

Defined in `dbt_project.yml` under `vars`, including:
- `raw_schema`
- `presentation_schema`
- `infra_schema`
- `adls_url_root`
- `storage_integration_name`
- `file_format_name`
- `managed_identity_tenant_id`

## Adding New Macro Behavior Safely

1. Update macro code in `macros/`.
2. Add or update tests that execute macro materialization via DuckDB/dbt harness.
3. Validate with pytest.
