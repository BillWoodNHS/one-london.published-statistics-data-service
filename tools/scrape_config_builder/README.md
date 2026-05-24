# Scrape Config Builder

Automatic YAML configuration generator for the scraper-driven ingestion system. The helper now runs in JSON v2 mode only and validates discovery against live web pages without downloading files.

## Quick Start

From the repo root:

```powershell
# JSON mode (per-dataset hints)
python tools/scrape_config_builder/scrape-config-helper.py --input-json tools/scrape_config_builder/helper_input/appointments-in-general-practice.json

# JSON directory mode (all datasets)
python tools/scrape_config_builder/scrape-config-helper.py --input-json-dir tools/scrape_config_builder/helper_input

# Optional: generate v2 helper inputs from legacy inventory CSV
python tools/scrape_config_builder/generate-helper-input-from-csv.py --inventory psds-file-inventory.csv
```

## Input Modes

### JSON Dataset Specs
Only supported mode for `scrape-config-helper.py`. Per-dataset JSON files in `helper_input/` directory.

Supports:
- Single dataset object
- Wrapper with `datasets: [...]` array
- `schema_version: "2.0"`
- Dataset-level `hints` object (`entry_structure`, `publication_date`, `subject_period`)
- Target-level `samples` array (`file_url`, `notes`)
- Per-target overrides: `preferred_link_selector`, `preferred_text_filter`, `sample_subpage_url`, `hints`

Example: [helper_input/appointments-in-general-practice.json](helper_input/appointments-in-general-practice.json)

### CSV Conversion Tool
Use `generate-helper-input-from-csv.py` to seed v2 helper JSON files from legacy inventory CSV data.

```powershell
python tools/scrape_config_builder/generate-helper-input-from-csv.py \
  --inventory psds-file-inventory.csv \
  --output-dir tools/scrape_config_builder/helper_input \
  --dataset appointments-in-general-practice
```

## Output Files

Generated in `--output-dir` (default: `logs/local_helper`):

- `generated_configs/*.yaml` — Candidate scraper YAML configs ready for manual review and commit.
- `helper_suggestions.csv` — Inferred selectors, patterns, and extension hints per sub-dataset.
- `matches_found.csv` — Live discovery validation results (URL, link text, publication date, subject period inference).
- `normalized_input_specs/*.json` — Final normalized v2 input specs used by the run.

## Helper Input JSON Schema

Minimal required fields:
- `schema_version` — Must be `"2.0"`
- `dataset_id` — Slug identifier (for example `appointments-in-general-practice`)
- `entry_url` — Root listing page URL
- `targets` — Array of sub-dataset specifications

Per-target fields:
- `sub_dataset_id` — Sub-dataset identifier (defaults to `"default"`)
- `sample_subpage_url` — Optional URL to a release subpage
- `samples` — One or more sample files with `file_url` and optional `notes`
- `include_extensions` — File extensions to match (e.g., `["zip", "csv"]`)
- `preferred_link_selector` — Optional CSS selector override
- `preferred_text_filter` — Optional regex filter override
- `hints` — Optional target hints (`file_pattern`, `subject_period_pattern`, `fiscal_year_format`, `month_extraction`)

## Inference Behavior

1. **Publication dates** — Extracted from page metadata markers or link text using regex patterns. Marked as `link_text` source in output YAML.
2. **Subject periods** — The generated YAML now includes a `subject_period` rule block with prioritized detection sources:
   1. `file_name` (closest to file)
   2. `url_segment`
   3. `page_text` (page elements from which links were discovered)
   This aligns runtime extraction with partitioning needs when subject period differs from publication date.
3. **Sub-page links** — Inferred from stable URL path tokens (year/month slugs). Can be overridden via `preferred_link_selector`.
4. **File patterns** — Extracted from example file URLs and generalized to regex for broad matching.

## Generated YAML Subject Period Rules

The helper emits this shape:

```yaml
subject_period:
  rules:
    - source: file_name
      pattern: <month-year regex>
    - source: url_segment
      pattern: <month-year regex>
    - source: page_text
      pattern: <month-year regex>
```

The function app evaluates rules top-to-bottom and uses the first successful normalized value (YYYYMM).

## Migration Path

1. **Generate v2 helper inputs from CSV** with `generate-helper-input-from-csv.py`
2. **Tune JSON per dataset** (samples, hints, overrides)
3. **Run `scrape-config-helper.py`** with `--input-json` or `--input-json-dir`

## Example Workflow

```powershell
# 1. Generate v2 helper input from CSV (optional)
python tools/scrape_config_builder/generate-helper-input-from-csv.py \
  --inventory psds-file-inventory.csv \
  --dataset appointments-in-general-practice

# 2. Edit helper JSON and add samples/hints as needed

# 3. Run helper with v2 JSON
python tools/scrape_config_builder/scrape-config-helper.py \
  --input-json tools/scrape_config_builder/helper_input/appointments-in-general-practice.json \
  --output-dir logs/scrape_run_1

# 4. Review generated YAML and match quality
# - Open logs/scrape_run_1/generated_configs/appointments-in-general-practice.yaml
# - Check logs/scrape_run_1/matches_found.csv
```

## Notes

- The tool does **not download files**; it validates discovery patterns only.
- Publication dates and subject periods are inferred but can be improved with hints and additional samples in JSON v2 input.
- The generated YAML configs are **candidates** and should be manually reviewed before committing.
- CSV is supported only through `generate-helper-input-from-csv.py`; the main helper accepts JSON v2 only.
