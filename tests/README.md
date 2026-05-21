# Tests

This folder contains unit and integration tests for ingestion and dbt behavior.

## Contents

- `test_manifest_loader.py`: Manifest contract checks.
- `test_adls_pathing.py`: Path partition and isolation behavior.
- `test_manual_source_discovery.py`: Manual fallback discovery behavior.
- `test_duckdb_revision_logic.py`: Revision selection logic.
- `test_duckdb_column_aliasing.py`: dbt macro aliasing validation via DuckDB.
- `test_web_to_duckdb_e2e.py`: Real web-backed end-to-end tests.
- `dbt_macro_harness.py`: Helper to call dbt macro operations from tests.
- `fixtures/`: Test manifests and dbt profile fixtures.

## Running Tests

Basic:

```powershell
python -m pytest -q
```

Include web-backed tests:

```powershell
$env:RUN_WEB_E2E = 'true'
python -m pytest -q tests/test_web_to_duckdb_e2e.py
Remove-Item Env:RUN_WEB_E2E -ErrorAction SilentlyContinue
```

## Adding Tests for New Configuration

1. Add or update manifest fixtures in `fixtures/manifests/`.
2. Add scenario coverage in focused test files.
3. Prefer assertions on behavior and contracts, not incidental formatting.
