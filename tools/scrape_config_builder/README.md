# Scrape Config Builder

Automatic YAML configuration generator for the scraper-driven ingestion system. Converts JSON dataset specifications into YAML configs that drive file discovery. The helper validates discovery patterns against live web pages without downloading files.

**Schema Support:**
- **v0.1** (recommended): Multi-page contexts with archive/sibling discovery (`source_pages`, `page_role`, `sibling_discovery`)
- **v2.0** (legacy): Single-page mode with optional subpage navigation (`samples`, `sample_subpage_url`)

## Quick Start

From the repo root:

```powershell
# JSON directory mode (all datasets, auto-detects schema version)
python tools/scrape_config_builder/scrape-config-helper.py --input-json-dir tools/scrape_config_builder/helper_input

# Single dataset
python tools/scrape_config_builder/scrape-config-helper.py --input-json tools/scrape_config_builder/helper_input/appointments-in-general-practice.json

# Single dataset (validate + generate + matches summary)
./tools/scrape_config_builder/run-helper.ps1 -InputJson tools/scrape_config_builder/helper_input/appointments-in-general-practice.json

# Promote latest generated YAML to config/datasets
python tools/scrape_config_builder/promote-generated-configs.py --dataset appointments-in-general-practice

# Promote latest generated YAML to config/datasets (PowerShell wrapper)
./tools/scrape_config_builder/promote-generated-configs.ps1 -Dataset appointments-in-general-practice

# Optional: generate v2 helper inputs from legacy inventory CSV
python tools/scrape_config_builder/generate-helper-input-from-csv.py --inventory psds-file-inventory.csv
```

## Input Schemas

### Schema v0.1 (Multi-page Discovery)
**Purpose**: Support datasets split across multiple page contexts (entry page, archive pages, subject-period-specific pages). Enable automatic sibling page discovery for new releases.

**Required fields**:
- `schema_version: "0.1"`
- `dataset_id`
- `entry_url`
- `targets[].sub_dataset_id`
- `targets[].sample_pages[]` — Array of page contexts to scrape

Per `sample_page`:
- `page_url` — URL to scrape
- `page_role` — `default` | `archive` | `sub_dataset_dedicated` | `subject_period_index` — Descriptive metadata copied to YAML (not used for scraper branching today)
- `partitioning_strategy` — `none` | `subject_period` | `mixed` — Helper metadata; sibling discovery auto-enable currently keys off `subject_period`/`mixed`
- `samples[]` — Sample file URLs with optional `notes`

**Target-level controls**:
- `hints.archive_pattern` — `none` | `sibling_pages_by_subject_period` — Controls whether helper emits `sibling_discovery.enabled: true`
- `include_extensions` — Optional but strongly recommended file types (otherwise inferred from samples)
- `preferred_link_selector`, `preferred_text_filter` — Optional CSS/regex overrides

**Example v0.1**: [helper_input/data-quality-maturity-index.json](helper_input/data-quality-maturity-index.json)

### Schema v2.0 (Legacy Single-Page)
**Purpose**: Original schema; still supported for backward compatibility.

**Supports**:
- Single dataset object or `datasets: [...]` array
- `schema_version: "2.0"`
- Dataset-level `hints` object
- Target-level `samples` array + optional `sample_subpage_url`
- Per-target overrides: `preferred_link_selector`, `preferred_text_filter`, `hints`

**Example v2.0**: [helper_input/appointments-in-general-practice.json](helper_input/appointments-in-general-practice.json)

### CSV Conversion Tool
Use `generate-helper-input-from-csv.py` to seed v2 helper JSON files from legacy inventory CSV data.

```powershell
python tools/scrape_config_builder/generate-helper-input-from-csv.py \
  --inventory psds-file-inventory.csv \
  --output-dir tools/scrape_config_builder/helper_input \
  --dataset appointments-in-general-practice
```

## Output Files

Generated in `--output-dir` (default: `tools/scrape_config_builder/helper_generated`) using:

`<output-dir>/<dataset_id>/run-<timestamp>/`

Each run folder contains:

- `generated_configs/*.yaml` — Candidate scraper YAML configs ready for manual review and promotion.
  - v0.1 JSON inputs → v0.1 YAML with `source_pages` array and `sibling_discovery` config
  - v2.0 JSON inputs → v2.0 YAML with `scrape_steps` only (legacy)
- `reports/helper_suggestions.csv` — Inferred selectors, patterns, and extension hints per sub-dataset.
- `reports/matches_found.csv` — Live discovery validation results (URL, link text, publication date, subject period inference).
- `reports/normalized_input_specs/*.json` — Final normalized input specs used by the run (with inferred schemas).
- `metadata.json` — Run metadata and summary counts.

The helper mirrors each run to:

`<output-dir>/<dataset_id>/latest/`

This gives a stable path for operational scripts and future UI tooling.

## Promote Workflow

Recommended workflow:

1. Generate and validate with the helper.
2. Review files under `<dataset_id>/latest/generated_configs/` and `<dataset_id>/latest/reports/`.
3. Promote selected YAML files into `config/datasets`.

Promotion command examples:

```powershell
# Promote one dataset from latest
python tools/scrape_config_builder/promote-generated-configs.py --dataset appointments-in-general-practice

# Promote one dataset from latest (PowerShell wrapper)
./tools/scrape_config_builder/promote-generated-configs.ps1 -Dataset appointments-in-general-practice

# Promote multiple datasets from latest
python tools/scrape_config_builder/promote-generated-configs.py --dataset dataset-a --dataset dataset-b

# Promote multiple datasets from latest (PowerShell wrapper)
./tools/scrape_config_builder/promote-generated-configs.ps1 -Dataset dataset-a,dataset-b

# Promote from a specific run id
python tools/scrape_config_builder/promote-generated-configs.py --dataset dataset-a --run-id run-20260526T120000Z

# Promote from a specific run id (PowerShell wrapper)
./tools/scrape_config_builder/promote-generated-configs.ps1 -Dataset dataset-a -RunId run-20260526T120000Z

# Preview only
python tools/scrape_config_builder/promote-generated-configs.py --dataset dataset-a --dry-run

# Preview only (PowerShell wrapper)
./tools/scrape_config_builder/promote-generated-configs.ps1 -Dataset dataset-a -DryRun
```

## V0.1 Schema Details

### When to Use v0.1
Use v0.1 when:
- Dataset has files on **multiple page contexts** (entry page + archive page, or quarterly pages, etc.)
- Need **automatic sibling discovery** to detect new releases (e.g., new financial year pages)
- Files are **partitioned by subject period** across different URLs

### Sample Page Roles

| Page Role | Purpose | Example |
|-----------|---------|---------|
| `default` | Primary page context for this target. Can contain latest files and/or links to period pages. | Entry URL with latest files and/or sublinks to each period's files |
| `archive` | Historical releases; older files grouped together | `/archive` subpage with previous months |
| `sub_dataset_dedicated` | Dedicated to one sub-dataset only | Dataset-specific subdomain or folder |
| `subject_period_index` | Explicit label for an index/navigation page that mainly links to period pages | Index page with year/quarter/month links and little/no direct files |

`page_role` is currently descriptive only. It is preserved in YAML for readability/review, but the scraper does not branch behavior by role.

### Partitioning Strategies

| Strategy | Meaning | Sibling Discovery Use |
|----------|---------|----------------------|
| `none` | Files not partitioned by subject period | Not applicable (disabled) |
| `subject_period` | Files split across pages by month/year | Helper can auto-enable sibling discovery when `hints.archive_pattern` is `sibling_pages_by_subject_period` |
| `mixed` | Combination of subject-period partitioning and other navigation patterns | Treated like `subject_period` for helper auto-enable |

### Archive Pattern Hints

For v0.1, archive behavior is controlled by `targets[].hints.archive_pattern`:

| Archive Pattern | Sibling Discovery Strategy | Generated YAML Config |
|-----------------|----------------------------|-----------------------|
| `none` | Single page only | `sibling_discovery.enabled: false` |
| `sibling_pages_by_subject_period` | Follow subject-period links (FY/month) from each seed page | `enabled: true`, `link_selector: a[href]`, `url_pattern: null`, `text_pattern: null`, `max_pages` set by helper |

Any other archive hint strings are currently treated as unsupported/no-op for v0.1 generation.

### v0.1 Property Usage Map (JSON -> YAML -> Scraper)

| JSON property | Generated YAML | Scraper use today |
|---|---|---|
| `entry_url` | `entry_url` | Used when needed for dataset context; direct discovery is driven by `targets[].source_pages[].page_url` |
| `targets[].sample_pages[].page_url` | `targets[].source_pages[].page_url` | Seed page URL fetched by scraper; sibling discovery starts from this page |
| `targets[].sample_pages[].page_role` | `targets[].source_pages[].page_role` | Preserved as metadata only (no branching behavior) |
| `targets[].sample_pages[].partitioning_strategy` | `targets[].source_pages[].partitioning_strategy` | Preserved as metadata; helper checks this when deciding sibling enablement |
| `targets[].preferred_link_selector` | `targets[].source_pages[].scrape_steps[].link_selector` | CSS selector used to extract candidate links/files |
| `targets[].preferred_text_filter` | `targets[].source_pages[].scrape_steps[].text_filter` | Regex filter on link text |
| `targets[].include_extensions` | `targets[].source_pages[].scrape_steps[].file_extensions` | Extension filter for candidate URLs |
| `targets[].hints.archive_pattern` | `targets[].source_pages[].sibling_discovery.enabled` (+ defaults) | Enables sibling-page expansion when set to `sibling_pages_by_subject_period` and partitioning is `subject_period`/`mixed` |
| Helper-generated sibling defaults | `sibling_discovery.link_selector/url_pattern/text_pattern/max_pages` | `link_selector` used to collect sibling links; patterns optional; `max_pages` caps sibling traversal |

### How Function App Uses v0.1 YAML

The scraper (`function_app/src/scraper.py`) processes v0.1 YAML as follows:

1. **Load targets**: Iterate `targets[].sub_dataset_id`
2. **For each target, process `source_pages[]` array**:
   - Visit each `source_page.page_url`
   - Apply `scrape_steps[]` with CSS selectors and regex filters to find files
   - **If `sibling_discovery.enabled: true`**:
     - Extract page links using `link_selector` CSS selector
     - Filter candidate links with `url_pattern` and `text_pattern` regex
  - Visit matching sibling pages discovered from the seed page (single-hop list, capped by `max_pages`)
     - Collect files from each sibling page with same scrape_steps
3. **Deduplicate**: Remove duplicate files across all source pages by `(sub_dataset_id, canonical_url)`
4. **Return**: Consolidated file list for ingestion

### Example v0.1 JSON → v0.1 YAML Flow

**Input JSON** (helper_input/data-quality-maturity-index.json):
```json
{
  "schema_version": "0.1",
  "dataset_id": "data-quality-maturity-index",
  "targets": [
    {
      "sub_dataset_id": "with-did",
      "hints": {
        "archive_pattern": "sibling_pages_by_subject_period"
      },
      "sample_pages": [
        {
          "page_url": "https://.../data-quality",
          "page_role": "default",
          "partitioning_strategy": "none",
          "samples": [{"file_url": "...dqmi_99_did.csv"}]
        },
        {
          "page_url": "https://.../data-quality/archive",
          "page_role": "archive",
          "partitioning_strategy": "subject_period",
          "samples": [
            {"file_url": "...dqmi_98_did.csv"},
            {"file_url": "...dqmi_97_did.csv"}
          ]
        }
      ]
    }
  ]
}
```

**Generated v0.1 YAML** (config/datasets/data-quality-maturity-index.yaml):
```yaml
targets:
  - sub_dataset_id: with-did
    source_pages:
      - page_url: https://.../data-quality
        page_role: default
        partitioning_strategy: none
        scrape_steps:
          - link_selector: a[href*='did']
            text_filter: DQMI.*CSV
            file_extensions: [csv]
        sibling_discovery:
          enabled: false
      - page_url: https://.../data-quality/archive
        page_role: archive
        partitioning_strategy: subject_period
        scrape_steps:
          - link_selector: a[href*='did']
            text_filter: DQMI.*CSV
            file_extensions: [csv]
        sibling_discovery:
          enabled: true
          link_selector: a[href]
          url_pattern: (jan|feb|mar|...|dec)[-_]?(2024|2025|2026)
          text_pattern: (FY|Q|Month)\s*(2024.*|2025.*)
          max_pages: 25
```

## V2.0 Schema (Legacy)

**Minimal required fields**:
- `schema_version: "2.0"`
- `dataset_id`
- `entry_url`
- `targets` with `sub_dataset_id` and `samples`

### Per-Target Fields (v2.0)
- `sample_subpage_url` — Optional URL to a release subpage (two-step navigation)
- `samples` — One or more sample files with `file_url` and optional `notes`
- `include_extensions` — File extensions to match (e.g., `["zip", "csv"]`)
- `preferred_link_selector` — Optional CSS selector override
- `preferred_text_filter` — Optional regex filter override
- `hints` — Optional target hints

### Per-Dataset Hints (v2.0)

| Field | How it is used now | Recommendation |
|-------|-------------------|-----------------|
| `entry_structure` | Stored in normalized output for traceability. Not used directly to build selectors. | Keep short and factual. Useful for humans reviewing `normalized_input_specs/*.json`. |
| `publication_date` | Stored in normalized output. Not used directly in selector generation. | Describe where date is visible (link text, page text, metadata). |
| `subject_period` | Used as an input signal when inferring `subject_period_pattern_type` if no explicit target-level type is provided. | Include month/year clues from real filenames or URLs. |

### Per-Target Fields (v2.0)

| Field | How it is used now | Recommendation |
|-------|-------------------|-----------------|
| `samples[].file_url` | Required. Drives extension inference and subject-period pattern inference. | Provide at least 2 recent samples where possible. |
| `samples[].notes` | Included in pattern inference text. If notes contain `formatted report` or `multiple tabs`, target is skipped. | Use concise notes. Avoid skip phrases unless intentional. |
| `sample_subpage_url` | If present, helper adds an initial navigation scrape step before file matching. | Set this when files are on release subpages (two-step navigation). |
| `include_extensions` | Primary file-type filter on final scrape step. | Always set explicitly (`csv`, `zip`, `xlsx`, `ods`) for predictable matching. |
| `preferred_link_selector` | Used only for the first (subpage navigation) step, and only when `sample_subpage_url` is present. | Use for release-page navigation selectors, not final file selectors. |
| `preferred_text_filter` | Used as file text filter only when no extension filter is applied on final step. | Prefer `include_extensions` first. Add text filter when many same-extension links exist. |
| `hints.subject_period_pattern` | Strongest hint for subject-period type, but only if one of: `fiscal_year_and_month`, `compact_month_year`, `month_year`. | Use one of those exact values. This is the most reliable hint. |
| `hints.file_pattern` | Stored in normalized output and suggestion context. Not directly compiled into final YAML rule. | Treat as documentation/supporting context, not a hard override. |
| `hints.fiscal_year_format` | Signal text for subject-period type inference when explicit type is absent. | Add when data uses fiscal year labels (for example `2025-26`). |
| `hints.month_extraction` | Signal text for subject-period type inference when explicit type is absent. | Describe where month/year appears (file name, URL segment, page text). |

## Precedence and Practical Rules (v2.0)

1. `hints.subject_period_pattern` (valid value) wins for subject-period type.
2. Otherwise, type is inferred from sample URLs and hint text.
3. `include_extensions` strongly constrains file matching and is applied on the final scrape step.
4. `preferred_link_selector` only affects subpage navigation (when `sample_subpage_url` exists).
5. Targets with notes containing `formatted report` or `multiple tabs` are skipped.

## Recommended Authoring Patterns

### For v0.1 (Multi-Page Discovery)

1. Use `sample_pages[]` when dataset has **multiple page contexts**.
2. Set `page_role` to accurately describe each page's lifecycle role.
3. Set `partitioning_strategy` based on how files are organized on that page.
4. If sibling discovery is needed, set `targets[].hints.archive_pattern` to `sibling_pages_by_subject_period`; helper auto-enables `sibling_discovery.enabled: true` in generated YAML.
5. Provide 2-3 sample files from each page context to ensure all discovery paths are tested.

### Common Web Patterns (v0.1)

#### Pattern A: Entry page links to monthly/quarterly period pages

Use this when the landing page is mostly a release index and each period page contains the files.

Recommended setup:
1. Set `sample_pages[0].page_url` to the dataset `entry_url` for each target (this is the sibling-discovery seed).
2. Set `partitioning_strategy` to `subject_period` (or `mixed` if needed).
3. Set `targets[].hints.archive_pattern` to `sibling_pages_by_subject_period`.
4. Use `preferred_link_selector`/`preferred_text_filter` to match files on period pages.
5. Use `page_role: default` or `page_role: subject_period_index` interchangeably for readability; behavior is currently the same.

When to use `subject_period_index`:
- Use it when you want to explicitly document that a page is primarily navigational (index of period pages) rather than a direct file page.
- It does not currently alter scraper behavior; it helps human review and future-proofing.

### For v2.0 (Legacy Single-Page)

1. Set `sample_subpage_url` **only** when a release page must be visited first.
2. Provide 2 to 3 realistic `samples` across adjacent months.
3. Always set `include_extensions` explicitly.
4. Use `hints.subject_period_pattern` with a valid enum when you know the pattern.
5. Keep text hints clear and literal; avoid ambiguous prose.

## Examples

### V0.1 Example: Multi-page with Archive Discovery

[helper_input/data-quality-maturity-index.json](helper_input/data-quality-maturity-index.json):
```json
{
  "schema_version": "0.1",
  "dataset_id": "data-quality-maturity-index",
  "dataset_name": "Data Quality Maturity Index",
  "entry_url": "https://digital.nhs.uk/data-and-information/.../data-quality",
  "targets": [
    {
      "sub_dataset_id": "with-did",
      "hints": {
        "archive_pattern": "sibling_pages_by_subject_period"
      },
      "sample_pages": [
        {
          "page_url": "https://digital.nhs.uk/data.../data-quality",
          "page_role": "default",
          "partitioning_strategy": "none",
          "samples": [
            {
              "file_url": "https://digital.nhs.uk/.../dqmi_99_csv-v2-did.csv",
              "notes": "Latest monthly CSV with DID included. Entry page"
            }
          ]
        },
        {
          "page_url": "https://digital.nhs.uk/data.../data-quality/archive",
          "page_role": "archive",
          "partitioning_strategy": "subject_period",
          "samples": [
            {
              "file_url": "https://digital.nhs.uk/.../dqmi_98_csv-v2-did.csv",
              "notes": "Previous monthly CSV with DID included. Archive page"
            }
          ]
        }
      ],
      "include_extensions": ["csv"],
      "preferred_link_selector": "a[href*='did']",
      "preferred_text_filter": "DQMI.*CSV.*DID"
    }
  ]
}
```

**Generated v0.1 YAML** includes:
- `source_pages[]` array with both default and archive roles
- `page_role: archive` on second page
- `partitioning_strategy: subject_period` on archive page
- `sibling_discovery.enabled: true` on archive page

### V2.0 Example: Two-step Release-Page Dataset (ZIP files)

```json
{
  "schema_version": "2.0",
  "dataset_id": "appointments-in-general-practice",
  "entry_url": "https://example.org/dataset/releases",
  "targets": [
    {
      "sub_dataset_id": "daily-counts",
      "sample_subpage_url": "https://example.org/dataset/march-2026",
      "samples": [
        {"file_url": "https://files.example.org/Appointments_Daily_Mar_26.zip"},
        {"file_url": "https://files.example.org/Appointments_Daily_Feb_26.zip"}
      ],
      "include_extensions": ["zip"],
      "hints": {
        "subject_period_pattern": "compact_month_year",
        "month_extraction": "Month-year token in file name"
      }
    }
  ]
}
```

### V2.0 Example: Direct-Link Dataset (CSV Files on Landing Page)

```json
{
  "schema_version": "2.0",
  "dataset_id": "health-check",
  "entry_url": "https://example.org/dataset",
  "targets": [
    {
      "sub_dataset_id": "monthly-publication",
      "samples": [
        {"file_url": "https://files.example.org/health-check-eng-Mar-2026.csv"},
        {"file_url": "https://files.example.org/health-check-eng-Feb-2026.csv"}
      ],
      "include_extensions": ["csv"],
      "preferred_text_filter": "health-check",
      "hints": {
        "subject_period_pattern": "month_year"
      }
    }
  ]
}
```

### V2.0 Example: Fiscal-Year Plus Month Naming

```json
{
  "schema_version": "2.0",
  "dataset_id": "waiting-lists",
  "entry_url": "https://example.org/waiting-lists",
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

## Migration: v2.0 → v0.1

To migrate a dataset from v2.0 to v0.1 multi-page discovery:

1. **Identify page contexts**: Determine all distinct pages where files appear (entry, archive subpages, year-specific pages, etc.)
2. **Create `sample_pages[]` array**: Add one entry per page context with appropriate `page_role` and `partitioning_strategy`
3. **Move samples**: Distribute sample file URLs across the relevant `sample_pages` based on which page they come from
4. **Set `targets[].hints.archive_pattern`**: Use `sibling_pages_by_subject_period` when period pages should be discovered from seed pages
5. **Test**: Run helper and verify `matches_found.csv` shows all expected files from all page contexts

Example migration flow:

```json
// v2.0 (single page, optional subpage)
{
  "schema_version": "2.0",
  "targets": [{
    "sub_dataset_id": "monthly",
    "sample_subpage_url": "https://example.org/2026-march",
    "samples": [
      {"file_url": "https://.../monthly-mar-2026.csv"},
      {"file_url": "https://.../monthly-feb-2026.csv"}
    ]
  }]
}

// v0.1 (multiple pages with archive discovery)
{
  "schema_version": "0.1",
  "targets": [{
    "sub_dataset_id": "monthly",
    "hints": {
      "archive_pattern": "sibling_pages_by_subject_period"
    },
    "sample_pages": [
      {
        "page_url": "https://example.org",
        "page_role": "default",
        "partitioning_strategy": "none",
        "samples": [{"file_url": "https://.../monthly-mar-2026.csv"}]
      },
      {
        "page_url": "https://example.org/archive",
        "page_role": "archive",
        "partitioning_strategy": "subject_period",
        "samples": [{"file_url": "https://.../monthly-feb-2026.csv"}]
      }
    ]
  }]
}
```

## Inference Behavior

### Publication Dates
- Extracted from page metadata markers or link text using regex patterns
- Marked as `link_text` source in output YAML
- Prioritized: file links > page metadata

### Subject Periods
The generated YAML includes a `subject_period` rule block with prioritized detection sources:
1. `file_name` (closest to file)
2. `url_segment`
3. `page_text` (page elements from which links were discovered)

This aligns runtime extraction with partitioning needs when subject period differs from publication date.

### File Patterns
- Extracted from example file URLs and generalized to regex for broad matching
- Extensions inferred from samples when `include_extensions` is empty (v2.0 legacy)

### Sub-page Links (v2.0 Legacy)
- Inferred from stable URL path tokens (year/month slugs)
- Can be overridden via `preferred_link_selector`

## Function App: How v0.1 YAML is Interpreted

This section explains how the function app's file discovery engine uses v0.1 YAML.

### Scraper Execution Flow

[function_app/src/scraper.py](../function_app/src/scraper.py) processes v0.1 YAML targets as follows:

**1. Load and iterate targets**
```
for target in config.targets:
    sub_dataset_id = target.sub_dataset_id
    for source_page in target.source_pages:
        discover_from_page(source_page)
```

**2. For each source_page:**
- Fetch the page at `source_page.page_url` via HTTP GET
- Parse HTML using BeautifulSoup
- Apply each `scrape_step` sequentially:
  - Extract links using CSS selector (`link_selector`)
  - Filter by file extension (`file_extensions`)
  - Filter by regex pattern (`text_filter`)
  - Collect matching file URLs

**3. If sibling discovery enabled:**
```
if source_page.sibling_discovery.enabled:
    seed_page_url = source_page.page_url
    seed_page_html = fetched HTML from step 2
    
    sibling_urls = extract_candidate_links(
        seed_page_html,
        css_selector=sibling_discovery.link_selector
    )
    
    for sibling_url in sibling_urls:
        if matches(sibling_url, sibling_discovery.url_pattern) \
           or matches(link_text, sibling_discovery.text_pattern):
            if page_count < sibling_discovery.max_pages:
                apply_scrape_steps(sibling_url)
                page_count += 1
```

**4. Deduplication**
- After all source pages are scraped, deduplicate by `(sub_dataset_id, canonical_url)`
- Canonical URL normalized: strip whitespace, rstrip slashes, lowercase scheme
- Return consolidated file list for ingestion

### Understanding Page Roles During Discovery

`page_role` is currently descriptive metadata only. The scraper does not branch by role.

- **`default`**: General-purpose page context (landing page and/or period-linked page)
- **`archive`**: Historical page context label
- **`sub_dataset_dedicated`**: Dedicated page context for one sub-dataset
- **`subject_period_index`**: Explicitly marks a period index/navigation page

### Understanding Partitioning Strategy

`partitioning_strategy` is metadata in YAML. In helper generation, sibling auto-enable currently requires `subject_period` or `mixed` when archive pattern is set to subject-period sibling discovery.

- **`none`**: All files on single page; no sibling discovery needed (even if hint provided)
- **`subject_period`**: Files split by month/year across URLs; use with sibling discovery
- **`mixed`**: Complex layouts combining period partitioning with other navigation

## Example: DQMI V0.1 Workflow

Dataset: **data-quality-maturity-index**, Sub-dataset: **with-did**

### Input JSON
- `hints.archive_pattern: "sibling_pages_by_subject_period"` — Files grouped across related archive/period pages

### Generated YAML
- Two `source_pages`:
  1. Default entry page → `sibling_discovery.enabled: false` (single page, no siblings)
  2. Archive page → `sibling_discovery.enabled: true` with month-year patterns (multiple months, siblings by month)

### Scraper Execution
1. **Visit entry page** (`https://.../data-quality`)
   - Scrape with selector `a[href*='did']` and filter `DQMI.*CSV`
   - Find: current month's DID CSV file

2. **Visit archive page** (`https://.../data-quality/archive`)
   - Scrape with same selector and filter
   - Find: previous month's DID CSV (if paginated on same page)
   - **Sibling discovery**:
     - Extract all links from archive page
     - Filter for those matching month-year patterns (e.g., "march-2026", "FY-2025-26")
     - Visit up to 25 matching sibling pages
     - Re-apply scrape steps on each sibling
     - Collect files from all visited pages

3. **Deduplicate** across both entry and archive contexts
4. **Result**: ~17 DID files from multiple months/years, vs ~1 without archive discovery

## CSV Conversion Tool (Optional)

Use `generate-helper-input-from-csv.py` to seed v2.0 helper JSON files from legacy inventory CSV data:

```powershell
python tools/scrape_config_builder/generate-helper-input-from-csv.py \
  --inventory psds-file-inventory.csv \
  --output-dir tools/scrape_config_builder/helper_input \
  --dataset appointments-in-general-practice
```

Output: Generates `helper_input/appointments-in-general-practice.json` with v2.0 schema extracted from CSV rows.
