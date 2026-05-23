# Scrape Config Builder

Automatic YAML configuration generator for the scraper-driven ingestion system. This tool infers scraper patterns from helper metadata (CSV inventory or per-dataset JSON specs), generates candidate YAML configs, and validates discovery against live web pages without downloading files.

## Quick Start

From the repo root:

```powershell
# CSV mode (bulk seed from inventory)
python tools/scrape_config_builder/build_scrape_configs_from_inventory.py --inventory psds-file-inventory.csv --dataset appointments-in-general-practice

# JSON mode (per-dataset hints)
python tools/scrape_config_builder/build_scrape_configs_from_inventory.py --input-json tools/scrape_config_builder/helper_input/appointments-in-general-practice.json

# JSON directory mode (all datasets)
python tools/scrape_config_builder/build_scrape_configs_from_inventory.py --input-json-dir tools/scrape_config_builder/helper_input
```

## Input Modes

### CSV Inventory
Legacy compatibility mode. Reads a CSV with columns: dataset name, parent link, sub-link, sub-collection, target file, notes. Useful for bulk seed runs.

CSV inputs are converted into normalized dataset specs internally.

### JSON Dataset Specs
New first-class mode. Per-dataset JSON files in `helper_input/` directory.

Supports:
- Single dataset object
- Wrapper with `datasets: [...]` array
- Optional hints: `publication_date_hint`, `subject_period_hint`, `subpage_link_hint`
- Per-target overrides: `preferred_link_selector`, `preferred_text_filter`

Example: [helper_input/appointments-in-general-practice.json](helper_input/appointments-in-general-practice.json)

### Mixed Mode
Combine CSV + JSON. JSON dataset specs override CSV-derived defaults by `dataset_id`.

```powershell
python tools/scrape_config_builder/build_scrape_configs_from_inventory.py \
  --inventory psds-file-inventory.csv \
  --input-json tools/scrape_config_builder/helper_input/appointments-in-general-practice.json \
  --dataset appointments-in-general-practice
```

## Output Files

Generated in `--output-dir` (default: `logs/local_helper`):

- `generated_configs/*.yaml` — Candidate scraper YAML configs ready for manual review and commit.
- `helper_suggestions.csv` — Inferred selectors, patterns, and extension hints per sub-dataset.
- `matches_found.csv` — Live discovery validation results (URL, link text, publication date, subject period inference).
- `normalized_input_specs/*.json` — Final normalized input specs used by the run. Useful for migration from CSV to JSON-first workflows.

## Helper Input JSON Schema

Minimal required fields:
- `dataset_id` — Slug identifier (e.g., `appointments-in-general-practice`)
- `entry_url` — Root listing page URL
- `targets` — Array of sub-dataset specifications

Optional metadata hints:
- `dataset_name` — Human-readable name
- `publication_date_hint` — Notes on how publication dates appear
- `subject_period_hint` — Notes on report period scope
- `subpage_link_hint` — Notes on sub-page URL patterns

Per-target fields:
- `sub_dataset_id` — Sub-dataset identifier (defaults to `"default"`)
- `sample_subpage_url` — URL to a monthly/release subpage (optional)
- `sample_file_url` — Example file URL to infer pattern
- `notes` — Human notes (e.g., "ZIP archive", "formatted report")
- `include_extensions` — File extensions to match (e.g., `["zip", "csv"]`)
- `preferred_link_selector` — Optional CSS selector override
- `preferred_text_filter` — Optional regex filter override

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

1. **Start with CSV** (bulk seed from inventory)
2. **Inspect normalized_input_specs/*.json** (shows how CSV was converted)
3. **Copy/tune JSON per dataset** (add hints, overrides)
4. **Move to JSON-only workflows** (fewer dependencies on fragile CSV formats)

## Example Workflow

```powershell
# 1. Initial CSV run
python tools/scrape_config_builder/build_scrape_configs_from_inventory.py \
  --inventory psds-file-inventory.csv \
  --dataset appointments-in-general-practice \
  --output-dir logs/scrape_run_1

# 2. Review generated YAML and matches
# - Open logs/scrape_run_1/generated_configs/appointments-in-general-practice.yaml
# - Check logs/scrape_run_1/matches_found.csv for any missing or noisy matches

# 3. Copy normalized spec for customization
cp logs/scrape_run_1/normalized_input_specs/appointments-in-general-practice.json \
   tools/scrape_config_builder/helper_input/appointments-in-general-practice.json

# 4. Edit JSON to add hints and overrides
# - Add subject_period_hint
# - Add preferred_link_selector per target if defaults are noisy

# 5. Re-run with JSON
python tools/scrape_config_builder/build_scrape_configs_from_inventory.py \
  --input-json tools/scrape_config_builder/helper_input/appointments-in-general-practice.json \
  --output-dir logs/scrape_run_2

# 6. Compare matches
# - Verify improvements in logs/scrape_run_2/matches_found.csv
```

## Notes

- The tool does **not download files**; it validates discovery patterns only.
- Publication dates and subject periods are inferred but can be overridden in the JSON input.
- The generated YAML configs are **candidates** and should be manually reviewed before committing.
- CSV inventory reads are backwards-compatible; CSV is optional when JSON inputs are provided.
