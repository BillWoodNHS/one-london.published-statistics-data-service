# V0.1 Schema Documentation: Complete Overview

**Last Updated**: May 25, 2026  
**Status**: ✅ Stable — All 11 datasets validated; backward compatible with v2.0

---

## What Changed

### Problem Solved
Before v0.1, datasets with files on multiple pages (entry + archive + year-specific pages) required:
- Manual specification of all subpage URLs in helper JSON
- No automatic discovery of new releases (new fiscal year pages, etc.)
- Limited to files on explicitly named pages

**Result**: DQMI detected ~3 files (current month only); missed 16+ previous months

### Solution: V0.1 Schema
Introduces:
- **`source_pages[]` array** — Describe ALL page contexts (entry, archive, subject-period pages) in one place
- **`page_role` field** — `default` | `archive` | `sub_dataset_dedicated` | `subject_period_index`
- **`partitioning_strategy` field** — `none` | `subject_period` | `pagination` | `mixed`
- **`sibling_discovery` config** — Automatic traversal of related pages (new months, fiscal years, quarters)
- **`archive_pattern_hint`** — Helper auto-enables discovery based on dataset structure

**Result**: DQMI now detects **19 files** (current month + all previous months) — **633% improvement**

---

## Documentation Files

### 1. **Helper README** — [tools/scrape_config_builder/README.md](tools/scrape_config_builder/README.md)
**What it covers**:
- Quick start commands
- Schema v0.1 vs v2.0 overview
- V0.1 sample page roles and partitioning strategies
- Archive pattern hints explained
- V0.1 JSON → V0.1 YAML generation flow
- Helper output files (generated_configs, matches_found.csv)
- Per-field usage for both schemas
- Recommended authoring patterns
- Complete examples for all patterns
- Migration guide (v2.0 → v0.1)
- Inference behavior (publication dates, subject periods)

**Read this when**: Setting up new datasets or updating helper input JSON

### 2. **Schema Migration Guide** — [config/SCHEMA_MIGRATION_GUIDE.md](config/SCHEMA_MIGRATION_GUIDE.md)
**What it covers**:
- Why upgrade from v2.0 to v0.1 (with DQMI example)
- Schema structural changes in detail
- Migration checklist (6 steps)
- How to identify page contexts
- How to create v0.1 JSON input
- Archive pattern hints guide
- Verification workflow (test generation → check matches → commit)
- Real DQMI migration example showing v2.0 → v0.1 transformation
- Troubleshooting common issues
- Rollback procedure

**Read this when**: Migrating a dataset from v2.0 to v0.1

### 3. **YAML Execution Guide** — [config/YAML_V0P1_EXECUTION_GUIDE.md](config/YAML_V0P1_EXECUTION_GUIDE.md)
**What it covers**:
- Architecture overview (helper → manifest loader → scraper)
- Complete v0.1 YAML structure with field meanings
- `source_pages` array explained
- `page_role` lifecycle roles
- `partitioning_strategy` meanings
- `sibling_discovery` config in detail
- Scraper execution flow algorithm (step-by-step)
- `discover_from_page()` function details
- Deduplication logic
- DQMI real-world discovery example
- Performance considerations
- Debugging tips
- Backward compatibility with v2.0

**Read this when**: Understanding how scraper interprets YAML or debugging discovery issues

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     HELPER TOOL PHASE                       │
├─────────────────────────────────────────────────────────────┤
│  Input: JSON helper specs (v0.1 or v2.0)                  │
│    ↓                                                         │
│  tools/scrape_config_builder/helper_input/*.json            │
│    ↓                                                         │
│  scrape-config-helper.py                                    │
│    ├─ Auto-detects schema version                           │
│    ├─ Infers selectors & patterns from samples             │
│    ├─ Validates against live web pages (no download)       │
│    ↓                                                         │
│  Output:                                                     │
│    ├─ logs/*/generated_configs/*.yaml (v0.1 or v2.0)      │
│    ├─ logs/*/matches_found.csv (validation results)        │
│    ├─ logs/*/helper_suggestions.csv (inferred patterns)    │
│    └─ logs/*/normalized_input_specs/*.json (normalized)    │
└─────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│                   MANIFEST LOADING PHASE                    │
├─────────────────────────────────────────────────────────────┤
│  Input: Generated YAML files                                │
│    ↓                                                         │
│  config/datasets/*.yaml                                     │
│    ↓                                                         │
│  function_app/src/manifest_loader.py                        │
│    ├─ Auto-detects schema version (v0.1 or v2.0)          │
│    ├─ Parses into Python dataclass models                   │
│    ├─ Validates required fields                             │
│    ├─ Supports backward compat (v2.0 → v0.1 wrapping)     │
│    ↓                                                         │
│  Output: DatasetSeriesConfig & TargetConfig objects        │
└─────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│                  FILE DISCOVERY PHASE                       │
├─────────────────────────────────────────────────────────────┤
│  Input: Loaded config from manifest_loader                 │
│    ↓                                                         │
│  function_app/src/scraper.py                                │
│    ├─ For each target:                                      │
│    │  ├─ For each source_page (v0.1) or scrape_steps (v2.0):
│    │  │  ├─ Fetch page HTML                                 │
│    │  │  ├─ Apply scrape_steps (CSS select + filter)       │
│    │  │  ├─ If sibling_discovery.enabled (v0.1 only):     │
│    │  │  │  ├─ Extract candidate links                     │
│    │  │  │  ├─ Filter by URL & text patterns              │
│    │  │  │  ├─ Visit matching siblings (up to max_pages)  │
│    │  │  │  └─ Re-apply scrape_steps to each sibling      │
│    │  │  └─ Collect files from this page                   │
│    ├─ Deduplicate across all source_pages by canonical URL
│    ↓                                                         │
│  Output: FileDiscoveryResult (files with metadata)         │
└─────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│                    DBT INGESTION PHASE                      │
├─────────────────────────────────────────────────────────────┤
│  Input: FileDiscoveryResult                                 │
│    ↓                                                         │
│  dbt/models/... (unchanged by v0.1)                        │
│    ↓                                                         │
│  Ingest files to warehouse                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## V0.1 Capabilities Summary

### Page Roles

| Role | Purpose | Example | Lifecycle |
|------|---------|---------|-----------|
| **default** | Current releases | Entry landing page | Expected every run |
| **archive** | Historical releases | `/archive` subpage | Updated intermittently |
| **sub_dataset_dedicated** | Dataset-specific page | Dataset-specific URL | Expected for that dataset |
| **subject_period_index** | Navigation/index | Links to FY/quarter pages | Navigational only |

### Partitioning Strategies

| Strategy | Meaning | Sibling Discovery |
|----------|---------|-------------------|
| **none** | Single page, files not partitioned | Disabled |
| **subject_period** | Files split by month/year across pages | Enabled; extract subject-period tokens |
| **pagination** | Same period, multiple pages (page 1, 2, 3...) | Enabled; follow "next" links |
| **mixed** | Both pagination & subject-period | Enabled; combined logic |

### Archive Pattern Hints

| Hint | Strategy | Auto-Generated Pattern |
|------|----------|----------------------|
| **none** | Single page | No sibling discovery |
| **general_archive_subpage** | Fixed URL `/archive` | Extract month-year tokens |
| **sibling_pages_by_subject_period** | FY/Quarter/Month-specific URLs | FY: `2024-25`, `2025-26`; Quarter: `Q1-2026`, `Q2-2026` |
| **same_page_paginated** | Pagination within page | "next", "page 2", etc. |
| **mixed** | Combination | Multiple strategies combined |

---

## Validation Status

### Test Results (as of May 25, 2026)

✅ **Code Quality**
- Ruff linter: **0 violations** (all 12 E501 line-length issues fixed)
- Pytest: **6/6 tests pass**
  - test_manifest_loads_targets ✓
  - test_manual_source_discovery ✓
  - test_publication_datetime_and_dedupe ✓ (3 tests)
  - test_scraper_source_pages ✓

✅ **YAML Generation**
- Helper processed: **11 datasets**
- Files generated: **11 YAML configs**
  - New: 1 (data-quality-maturity-index)
  - Modified: 10 (regenerated from normalized JSON)
  - Removed: 0 (backward compatible)

✅ **File Detection (matches_found.csv)**
- No errors in any dataset
- **DQMI detected**: 19 files (up from ~3) — **633% improvement**
  - with-did: 17 files
  - without-did: 2 files
- All other datasets: **stable counts, no degradation**

✅ **Backward Compatibility**
- v2.0 YAML still supported via internal normalization
- All 11 generated configs valid (auto-detects schema)
- DBT models unchanged (zero impact downstream)

---

## Quick Start: Using V0.1

### For New Datasets (Use V0.1)

1. **Create JSON helper input** with `schema_version: "0.1"`
   ```json
   {
     "schema_version": "0.1",
     "dataset_id": "my-dataset",
     "targets": [{
       "sub_dataset_id": "monthly",
       "archive_pattern_hint": "general_archive_subpage",
       "sample_pages": [
         {"page_url": "https://...", "page_role": "default", ...},
         {"page_url": "https://.../archive", "page_role": "archive", ...}
       ]
     }]
   }
   ```

2. **Run helper**:
   ```bash
   python tools/scrape_config_builder/scrape-config-helper.py \
     --input-json-dir tools/scrape_config_builder/helper_input \
     --output-dir logs/my_run
   ```

3. **Review generated YAML**:
   - Check `logs/my_run/generated_configs/my-dataset.yaml`
   - Verify `source_pages` structure
   - Verify `sibling_discovery` config

4. **Validate matches**:
   - Check `logs/my_run/matches_found.csv`
   - Verify files from all page contexts detected
   - No errors or anomalies

5. **Commit**:
   ```bash
   cp logs/my_run/generated_configs/my-dataset.yaml config/datasets/
   git add config/datasets/my-dataset.yaml \
           tools/scrape_config_builder/helper_input/my-dataset.json
   ```

### For Existing V2.0 Datasets (Optional Upgrade)

Follow [config/SCHEMA_MIGRATION_GUIDE.md](config/SCHEMA_MIGRATION_GUIDE.md) for step-by-step migration.

---

## Key Files Modified/Created

### Documentation
- ✅ Updated: [tools/scrape_config_builder/README.md](tools/scrape_config_builder/README.md) — Comprehensive helper documentation with both schemas
- ✅ Created: [config/SCHEMA_MIGRATION_GUIDE.md](config/SCHEMA_MIGRATION_GUIDE.md) — Migration guide from v2.0 to v0.1
- ✅ Created: [config/YAML_V0P1_EXECUTION_GUIDE.md](config/YAML_V0P1_EXECUTION_GUIDE.md) — Function app YAML interpretation

### Code (Previously Completed)
- ✅ Updated: `function_app/src/models.py` — Added `SiblingDiscoveryConfig`, `SourcePageConfig`
- ✅ Updated: `function_app/src/manifest_loader.py` — v0.1 YAML parsing with backward compat
- ✅ Updated: `function_app/src/scraper.py` — Multi-page discovery + sibling traversal + deduplication
- ✅ Updated: `tools/scrape_config_builder/scrape-config-helper.py` — v0.1 YAML generation

### Config
- ✅ Updated: [config/datasets/data-quality-maturity-index.yaml](config/datasets/data-quality-maturity-index.yaml) — Migrated to v0.1 with `source_pages` and archive discovery

### Helper Input
- ✅ Updated: [tools/scrape_config_builder/helper_input/data-quality-maturity-index.json](tools/scrape_config_builder/helper_input/data-quality-maturity-index.json) — Migrated to v0.1 with `sample_pages` and `archive_pattern_hint`

---

## Next Steps (Optional)

### Potential Enhancements
1. Migrate remaining 10 v2.0 datasets to v0.1 (if they have archive pages)
2. Enable sibling discovery in DQMI archive page (currently disabled; set `enabled: true` to auto-detect month-year pages)
3. Add intelligent pagination detection for datasets with "next page" links
4. Implement cross-run caching for subject-period pages

### Known Limitations
- Sibling discovery limited to 25 pages max (configurable in YAML)
- No recursive sibling discovery (siblings of siblings)
- Manual regex pattern tuning sometimes needed for niche datasets

---

## Support & Questions

**For questions about**:
- **Helper input JSON format**: See [tools/scrape_config_builder/README.md](tools/scrape_config_builder/README.md) → "V0.1 Schema Details"
- **Migrating datasets**: See [config/SCHEMA_MIGRATION_GUIDE.md](config/SCHEMA_MIGRATION_GUIDE.md)
- **How scraper executes YAML**: See [config/YAML_V0P1_EXECUTION_GUIDE.md](config/YAML_V0P1_EXECUTION_GUIDE.md)
- **Specific dataset issues**: Check `logs/*/matches_found.csv` for discovery errors

---

**Version**: v0.1 YAML Schema  
**Release Date**: May 25, 2026  
**Stability**: Stable / Production Ready  
**Backward Compatible**: Yes (v2.0 still supported)

## June 2026 Contract Update

- Storage paths now partition by download time (`download_year`, `download_month`, `downloaded_at`) rather than `subject_period`.
- Sidecar metadata now stores `_SUBJECT_PERIOD_FROM` and `_SUBJECT_PERIOD_TO` (inclusive timestamps) plus inference diagnostics.
- Target configs may include optional `period_coverage` hints to prioritize runtime period inference.
