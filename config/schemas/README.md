# Known schemas (local DuckDB e2e drift check only)

This folder holds **optional** known-column lists used by the local
end-to-end DuckDB simulation (`tools/local_dev/run_local_e2e.py` /
`tools/local_dev/load_csvs_to_duckdb.py`) to flag schema drift. It is a
developer-facing sanity check only:

- It never runs in the production Azure Function App ingestion path
  (`function_app/src/`) - production always uses schema evolution and loads
  every column it sees.
- It never blocks a local load or fails the e2e run - drift is logged as a
  warning and surfaced in `verify_local_run.py`'s summary report for a human
  to review.
- It is opt-in - a dataset with no file here, or a target/sub-table suffix
  missing from its file, is simply skipped (no warning, no error).

## File naming

One file per dataset, named to match the dataset's manifest file:

```
config/schemas/<dataset_id>.yaml
```

`<dataset_id>` must match the `dataset_id` field in the corresponding
`config/datasets/<dataset_id>.yaml` manifest exactly (this is also the
filename convention `config/datasets/` already uses, so the two folders
line up 1:1).

## Required shape

```yaml
schemas:
  <object_name_suffix>:
    columns:
      - "Column One"
      - "Column Two"
      - "Column Three"
```

- `schemas` is the required top-level key.
- Each key under `schemas` is an `object_name_suffix` - the same value used
  on a `target` or `sub_table` block in the dataset's manifest
  (`config/datasets/<dataset_id>.yaml`). This is the suffix used to name the
  DuckDB ingest table, e.g. a target with `object_name_suffix: AE_DEFAULT`
  loads into `INGEST.INGEST_AE_DEFAULT`, and its known schema goes under
  `schemas.AE_DEFAULT` here.
- `columns` is the list of expected column names (as they appear in the
  downloaded CSV header, case-sensitive) for that suffix. Order does not
  matter - the comparison is set-based.
- A dataset can have multiple targets and/or sub-tables; declare an entry
  per suffix you want checked. Suffixes you don't list are skipped.

## How drift is measured

For each loaded CSV, its actual column set is compared against the known
`columns` list using Jaccard distance:

```
drift_ratio = 1 - |known ∩ actual| / |known ∪ actual|
```

If `drift_ratio` exceeds the configured threshold (default `0.20`, i.e. more
than 20% different), a warning is recorded - it includes the table name, the
CSV file, and the known vs. actual columns. The threshold can be overridden
via `--schema-drift-threshold` on `run_local_e2e.py` /
`load_csvs_to_duckdb.py`.

## Example

For the manifest at
`config/datasets/accident-and-emergency-attendances-and-emergency-admissions.yaml`,
which declares a target with `object_name_suffix: AE_DEFAULT`, the matching
schema file is
`config/schemas/accident-and-emergency-attendances-and-emergency-admissions.yaml`:

```yaml
schemas:
  AE_DEFAULT:
    columns:
      - "Period"
      - "Org Code"
      - "Org Name"
      - "Total Attendances"
      - "Total Emergency Admissions"
```

When you add or update a dataset's expected columns, keep this list in sync
with what the source actually publishes - schema drift here is meant to
catch an unexpected change (e.g. a misconfigured scrape target or a source
restructuring its file), not to gate every legitimate column addition.
