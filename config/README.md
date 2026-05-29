# Configuration Folder

This folder contains ingestion configuration for supplier datasets.

## Contents

- `datasets/`: Manifest YAML files, typically one per data series.

## How to Add New Configuration

1. Add a new YAML file under `datasets/`.
2. Follow the required manifest contract used by `function_app/src/manifest_loader.py`.
3. Keep `series_id` stable over time; use `sub_dataset_id` to isolate files by subject area.
4. Set `targets[].object_name_suffix` explicitly so Snowflake object names remain stable even if dataset IDs change later.
5. Use only the suffix in YAML, not full object names. dbt applies the standard prefixes: `STG_`, `PIPE_`, `INGEST_`, and `RAW_`.
6. Set `targets[].adls_path_prefix` explicitly so the ADLS storage path remains stable even if dataset IDs change later. Use a relative path such as `series-id/sub-dataset-id` — no leading/trailing slashes, no `..`.
7. Validate with tests after adding the file.
