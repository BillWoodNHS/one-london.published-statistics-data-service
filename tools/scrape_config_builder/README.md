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

## How Hints Are Interpreted

This section describes how `scrape-config-helper.py` currently uses each hint in code.

### Dataset-level `hints`

| Field | How it is used now | Recommendation |
|---|---|---|
| `entry_structure` | Stored in normalized output for traceability. Not used directly to build selectors. | Keep short and factual. Useful for humans reviewing `normalized_input_specs/*.json`. |
| `publication_date` | Stored in normalized output. Not used directly in selector generation. | Describe where date is visible (link text, page text, metadata). |
| `subject_period` | Used as an input signal when inferring `subject_period_pattern_type` if no explicit target-level type is provided. | Include month/year clues from real filenames or URLs. |

### Target-level controls and hints

| Field | How it is used now | Recommendation |
|---|---|---|
| `samples[].file_url` | Required. Drives extension inference (when `include_extensions` is empty) and subject-period pattern inference. | Provide at least 2 recent samples where possible. |
| `samples[].notes` | Included in pattern inference text. If notes contain `formatted report` or `multiple tabs`, target is skipped. | Use concise notes. Avoid those skip phrases unless you want the target skipped. |
| `sample_subpage_url` | If present, helper adds an initial navigation scrape step before file matching. | Set this when files are on release subpages (two-step navigation). |
| `include_extensions` | Primary file-type filter on final scrape step. | Always set explicitly (`csv`, `zip`, `xlsx`, `ods`) for predictable matching. |
| `preferred_link_selector` | Used only for the first (subpage navigation) step, and only when `sample_subpage_url` is present. | Use for release-page navigation selectors, not final file selectors. |
| `preferred_text_filter` | Used as file text filter only when no extension filter is applied on final step. | Prefer `include_extensions` first. Add text filter when many same-extension links exist. |
| `hints.subject_period_pattern` | Strongest hint for subject-period type, but only if one of: `fiscal_year_and_month`, `compact_month_year`, `month_year`. | Use one of those exact values. This is the most reliable hint. |
| `hints.file_pattern` | Stored in normalized output and suggestion context. Not directly compiled into final YAML rule. | Treat as documentation/supporting context, not a hard override. |
| `hints.fiscal_year_format` | Signal text for subject-period type inference when explicit type is absent. | Add when data uses fiscal year labels (for example `2025-26`). |
| `hints.month_extraction` | Signal text for subject-period type inference when explicit type is absent. | Describe where month/year appears (file name, URL segment, page text). |

## Precedence and Practical Rules

1. `hints.subject_period_pattern` (valid value) wins for subject-period type.
2. Otherwise, type is inferred from sample URLs and hint text.
3. `include_extensions` strongly constrains file matching and is applied on the final scrape step.
4. `preferred_link_selector` only affects subpage navigation (when `sample_subpage_url` exists).
5. Targets with notes containing `formatted report` or `multiple tabs` are skipped.

## Recommended Authoring Pattern

1. Set `sample_subpage_url` only when a release page must be visited before file links.
2. Provide 2 to 3 realistic `samples` across adjacent months.
3. Always set `include_extensions` explicitly.
4. Use `hints.subject_period_pattern` with a valid enum when you know the pattern.
5. Keep text hints clear and literal; avoid ambiguous prose.

## Examples

### 1) Two-step release-page dataset (ZIP files)

```json
{
  "sub_dataset_id": "daily-counts",
  "sample_subpage_url": "https://example.org/dataset/march-2026",
  "samples": [
    {"file_url": "https://files.example.org/Appointments_Daily_Mar_26.zip"},
    {"file_url": "https://files.example.org/Appointments_Daily_Feb_26.zip"}
  ],
  "include_extensions": ["zip"],
  "preferred_link_selector": "",
  "preferred_text_filter": "",
  "hints": {
    "subject_period_pattern": "compact_month_year",
    "month_extraction": "Month-year token in file name"
  }
}
```

### 2) Direct-link dataset (CSV files on landing page)

```json
{
  "sub_dataset_id": "monthly-publication",
  "sample_subpage_url": "",
  "samples": [
    {"file_url": "https://files.example.org/health-check-eng-Mar-2026.csv"},
    {"file_url": "https://files.example.org/health-check-eng-Feb-2026.csv"}
  ],
  "include_extensions": ["csv"],
  "preferred_link_selector": "",
  "preferred_text_filter": "health-check",
  "hints": {
    "subject_period_pattern": "month_year"
  }
}
```

### 3) Fiscal-year plus month naming

```json
{
  "hints": {
    "subject_period": "File names include fiscal year and month (for example 2025-26-March)."
  },
  "targets": [
    {
      "sub_dataset_id": "monthly-publication",
      "samples": [
        {"file_url": "https://files.example.org/waiting-lists-2025-26-March.xlsx"}
      ],
      "include_extensions": ["xlsx"],
      "hints": {
        "subject_period_pattern": "fiscal_year_and_month",
        "fiscal_year_format": "YYYY-YY"
      }
    }
  ]
}
```

### 4) Intentionally skipping formatted report targets

```json
{
  "sub_dataset_id": "summary",
  "samples": [
    {
      "file_url": "https://files.example.org/summary.xlsx",
      "notes": "formatted report - multiple tabs"
    }
  ],
  "include_extensions": ["xlsx"]
}
```

The helper skips this target because it is a formatted report, not a direct ingestion file.

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
