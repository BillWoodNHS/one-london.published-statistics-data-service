# Configuration Folder

This folder contains ingestion configuration for supplier datasets.

## Contents

- `datasets/`: Manifest YAML files, typically one per data series.

## How to Add New Configuration

1. Add a new YAML file under `datasets/`.
2. Follow the required manifest contract used by `function_app/src/manifest_loader.py`.
3. Keep `series_id` stable over time; use `sub_dataset_id` to isolate files by subject area.
4. Validate with tests after adding the file.
