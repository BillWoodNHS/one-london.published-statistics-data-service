# YAML Schema Migration Guide: v2.0 → v0.1

**Purpose:** Guide dataset maintainers through upgrading dataset configs from legacy v2.0 (single-page discovery) to v0.1 (multi-page discovery with archive support).

---

## Why Upgrade to v0.1?

### Problem with v2.0
- **Single-page discovery only**: Cannot scrape from multiple page contexts (entry + archive + subject-period pages)
- **Manual page specification required**: To find files on archive pages, developer must specify `sample_subpage_url` explicitly
- **No automatic sibling discovery**: New releases (e.g., new fiscal year pages) require manual YAML updates
- **Limited file coverage**: Datasets with archived releases only find current month/year files

### Solution with v0.1
- **Multi-page contexts**: Describe all relevant pages (entry, archive, etc.) in single target via `source_pages[]` array
- **Automatic sibling discovery**: Enable `sibling_discovery` to find related pages by subject-period tokens, release links, pagination, etc.
- **Self-updating**: New releases detected automatically as new sibling pages appear
- **Comprehensive coverage**: Archive pages + entry page = all historical files + current files

### Real-World Improvement: DQMI Dataset

**Before (v2.0)**:
- Entry page config only → ~3 files detected (current month only)
- No archive page in YAML config → Missing previous months

**After (v0.1)**:
- Entry page config + archive page config with sibling discovery → **19 files detected** (current month + all previous months)
- **633% file count increase** with same scraper code and no additional manual maintenance

---

## Schema Changes: v2.0 → v0.1

### Key Structural Changes

| Aspect | v2.0 | v0.1 |
|--------|------|------|
| **Target files location** | Single page (entry_url + optional sample_subpage_url) | Multiple pages via `source_pages[]` array |
| **Page description** | No metadata (implicit landing page) | `page_role` + `partitioning_strategy` describe each page |
| **Multi-page discovery** | Manual: set `sample_subpage_url` to each subpage | Automatic: `sibling_discovery` config enables intelligent traversal |
| **Archive patterns** | Manual hints only (`hints.month_extraction`, etc.) | Explicit `archive_pattern_hint` + auto-generated sibling patterns |
| **Scrape steps** | Single `scrape_steps` array per target | Per-page `scrape_steps` (same logic, repeated per page context) |

### JSON Helper Input Changes

| Field | v2.0 | v0.1 | Migration |
|-------|------|------|-----------|
| `schema_version` | `"2.0"` | `"0.1"` | Update field |
| `targets[].samples` | Array on entry page only | Moved into `sample_pages[].samples` per page | Split samples across pages |
| `targets[].sample_subpage_url` | Optional archive page URL | Becomes second `source_page` with `page_role: archive` | Extract to separate page object |
| `targets[].archive_pattern_hint` | N/A | New field describing sibling discovery strategy | Add based on dataset structure |
| `targets[].sample_pages` | N/A | New array of page contexts (entry, archive, etc.) | Create from `samples` + `sample_subpage_url` |

### Generated YAML Changes

#### v2.0 Target Structure
```yaml
targets:
  - sub_dataset_id: monthly
    scrape_steps:
      - link_selector: a[href*='file']
        text_filter: monthly.*csv
        file_extensions: [csv]
```

#### v0.1 Target Structure
```yaml
targets:
  - sub_dataset_id: monthly
    source_pages:
      - page_url: https://example.org/data
        page_role: default
        partitioning_strategy: none
        scrape_steps:
          - link_selector: a[href*='file']
            text_filter: monthly.*csv
            file_extensions: [csv]
        sibling_discovery:
          enabled: false
          link_selector: a[href]
          url_pattern: null
          text_pattern: null
          max_pages: 25
      - page_url: https://example.org/data/archive
        page_role: archive
        partitioning_strategy: subject_period
        scrape_steps:
          - link_selector: a[href*='file']
            text_filter: monthly.*csv
            file_extensions: [csv]
        sibling_discovery:
          enabled: true
          link_selector: a[href]
          url_pattern: (jan|feb|...|dec)[-_]?(19\d{2}|20\d{2})
          text_pattern: (FY|Q|Month)\s*(19\d{2}|20\d{2})
          max_pages: 25
```

---

## Migration Checklist

### Step 1: Analyze Current v2.0 Config

Review your existing `config/datasets/your-dataset.yaml`:

```yaml
# Check these fields:
targets:
  - sub_dataset_id: ???
    scrape_steps: [...]        # ← Will become source_pages[0].scrape_steps
    # ... more targets
```

**Questions to answer:**
1. How many targets (sub_dataset_ids)? → Each gets its own v0.1 target with potentially multiple `source_pages`
2. Does this target have files on multiple page contexts (entry + archive + year-specific)? → If YES, this dataset is a v0.1 candidate
3. Are files on entry URL only? → v2.0 is fine; optional to upgrade
4. Are new releases discovered automatically or manually? → If manually (YAML updates), v0.1 would help

### Step 2: Identify Page Contexts

For each target, list all pages where files appear:

**Entry Page**:
- URL: (entry_url from dataset)
- Files: Current month/year release
- Page Role: `default`
- Partitioning: `none` (or `subject_period` if multiple months on same page)

**Archive Page(s)** (if applicable):
- URL: `/archive` subpage, `/releases` page, `/historical-data`, etc.
- Files: Previous months/years
- Page Role: `archive`
- Partitioning: `subject_period` (files grouped by month/year)

**Subject-Period Index** (if applicable):
- URL: `/2025-26` (fiscal year specific), `/Q1-2026` (quarter specific)
- Files: Filtered by subject period
- Page Role: `subject_period_index`
- Partitioning: `none` or `pagination`

### Step 3: Create v0.1 JSON Helper Input

Update `tools/scrape_config_builder/helper_input/your-dataset.json`:

```json
{
  "schema_version": "0.1",
  "dataset_id": "your-dataset",
  "entry_url": "https://...",
  "targets": [
    {
      "sub_dataset_id": "target-name",
      "archive_pattern_hint": "general_archive_subpage",
      "sample_pages": [
        {
          "page_url": "https://... entry page",
          "page_role": "default",
          "partitioning_strategy": "none",
          "samples": [
            {"file_url": "... current month file"}
          ]
        },
        {
          "page_url": "https://... archive page",
          "page_role": "archive",
          "partitioning_strategy": "subject_period",
          "samples": [
            {"file_url": "... previous month file"},
            {"file_url": "... another previous month file"}
          ]
        }
      ],
      "include_extensions": ["csv"],
      "preferred_link_selector": "a[href*='filter']",
      "preferred_text_filter": "dataset.*pattern"
    }
  ]
}
```

### Step 4: Verify Archive Pattern Hint

Choose the correct `archive_pattern_hint` for your dataset:

| Hint | When to Use | Example |
|------|------------|---------|
| `none` | Single page only; no archive discovery needed | All files on one landing page |
| `general_archive_subpage` | Archive page exists at predictable URL; contains files from multiple periods | `/archive` contains all previous months |
| `sibling_pages_by_subject_period` | Subject-period-specific pages appear on same URL structure | `/2024-25`, `/2025-26` (fiscal years); `/Q1-2026`, `/Q2-2026` (quarters) |
| `same_page_paginated` | Files paginated on single page ("next page", "page 2", etc.) | Release page with 100-file pagination |
| `mixed` | Combination of strategies | Files paginated within `/archive` subpage; also fiscal-year pages |

### Step 5: Generate and Test YAML

Run helper:
```powershell
python tools/scrape_config_builder/scrape-config-helper.py \
  --input-json-dir tools/scrape_config_builder/helper_input \
  --output-dir logs/migration_test
```

Check output:
- Open `logs/migration_test/generated_configs/your-dataset.yaml`
- Verify `source_pages` array has all expected pages
- Verify `page_role` and `partitioning_strategy` are correct
- Verify `sibling_discovery` is enabled where appropriate

Review discovery results:
- Open `logs/migration_test/matches_found.csv`
- Filter by `dataset_id = your-dataset`
- Verify files found from all page contexts (entry + archive + etc.)
- Compare to old v2.0 results: new count should be ≥ old count

### Step 6: Commit Generated YAML

If validation passes:
```bash
cp logs/migration_test/generated_configs/your-dataset.yaml config/datasets/your-dataset.yaml
git add config/datasets/your-dataset.yaml tools/scrape_config_builder/helper_input/your-dataset.json
git commit -m "chore: migrate your-dataset to v0.1 schema with multi-page discovery"
```

---

## Real Example: DQMI Migration

### v2.0 Config (Before)

**helper_input/data-quality-maturity-index.json** (v2.0):
```json
{
  "schema_version": "2.0",
  "dataset_id": "data-quality-maturity-index",
  "entry_url": "https://digital.nhs.uk/.../data-quality",
  "targets": [
    {
      "sub_dataset_id": "with-did",
      "samples": [
        {"file_url": "https://.../dqmi_99_csv-v2-did.csv"}
      ],
      "sample_subpage_url": "https://digital.nhs.uk/.../data-quality/archive",
      "include_extensions": ["csv"]
    }
  ]
}
```

**config/datasets/data-quality-maturity-index.yaml** (v2.0):
```yaml
targets:
  - sub_dataset_id: with-did
    scrape_steps:
      - link_selector: a[href$='.csv'][href*='did']
        text_filter: DQMI.*CSV.*DID
        file_extensions: [csv]
```

**Discovery Result**: ~3 files (entry page only; archive page ignored without sample there)

### v0.1 Config (After)

**helper_input/data-quality-maturity-index.json** (v0.1):
```json
{
  "schema_version": "0.1",
  "dataset_id": "data-quality-maturity-index",
  "entry_url": "https://digital.nhs.uk/.../data-quality",
  "targets": [
    {
      "sub_dataset_id": "with-did",
      "archive_pattern_hint": "general_archive_subpage",
      "sample_pages": [
        {
          "page_url": "https://digital.nhs.uk/.../data-quality",
          "page_role": "default",
          "partitioning_strategy": "none",
          "samples": [
            {"file_url": "https://.../dqmi_99_csv-v2-did.csv", "notes": "Current month"}
          ]
        },
        {
          "page_url": "https://digital.nhs.uk/.../data-quality/archive",
          "page_role": "archive",
          "partitioning_strategy": "subject_period",
          "samples": [
            {"file_url": "https://.../dqmi_98_csv-v2-did.csv", "notes": "Previous month"},
            {"file_url": "https://.../dqmi_97_csv-v2-did.csv", "notes": "Two months back"}
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

**config/datasets/data-quality-maturity-index.yaml** (v0.1):
```yaml
targets:
  - sub_dataset_id: with-did
    source_pages:
      - page_url: https://digital.nhs.uk/.../data-quality
        page_role: default
        partitioning_strategy: none
        scrape_steps:
          - link_selector: a[href*='did']
            text_filter: DQMI.*CSV.*DID
            file_extensions: [csv]
        sibling_discovery:
          enabled: false
      - page_url: https://digital.nhs.uk/.../data-quality/archive
        page_role: archive
        partitioning_strategy: subject_period
        scrape_steps:
          - link_selector: a[href*='did']
            text_filter: DQMI.*CSV.*DID
            file_extensions: [csv]
        sibling_discovery:
          enabled: true
          link_selector: a[href]
          url_pattern: (jan|feb|...|dec)[-_]?(2024|2025|2026)
          text_pattern: (FY|Q|Month)\s*(2024|2025|2026)
          max_pages: 25
```

**Discovery Result**: **19 files** (entry page + archive page with automatic month-year sibling pages)
- **Improvement**: 19 vs 3 = **633% increase**

---

## Troubleshooting

### Generated YAML has `sibling_discovery.enabled: false` when I need it enabled

**Cause**: Helper didn't recognize the archive pattern from samples provided.

**Fix**:
1. Verify `archive_pattern_hint` is set to non-`none` value
2. Add more diverse sample files (multiple months, different years)
3. Manually edit generated YAML to set `sibling_discovery.enabled: true` and adjust patterns

### File counts decreased after upgrade

**Cause**: Likely CSS selector or text filter is too restrictive on new page contexts.

**Fix**:
1. Check `matches_found.csv` for errors
2. Verify `preferred_link_selector` works on both entry and archive pages
3. Test selector manually on live pages using browser DevTools
4. Update `preferred_link_selector` or `preferred_text_filter` in JSON helper input
5. Re-run helper

### Sibling discovery finds too many false-positive pages

**Cause**: `url_pattern` or `text_pattern` is too loose.

**Fix**:
1. Review `matches_found.csv` for unexpected URLs
2. Tighten regex patterns manually in YAML
3. Reduce `max_pages` limit to avoid traversing unrelated pages

---

## Rollback to v2.0 (If Needed)

If v0.1 migration encounters blockers, revert to v2.0:

```bash
# Revert JSON helper input
git checkout HEAD -- tools/scrape_config_builder/helper_input/your-dataset.json

# Revert YAML config
git checkout HEAD -- config/datasets/your-dataset.yaml
```

---

## Additional Resources

- **Scrape Config Builder README**: [tools/scrape_config_builder/README.md](../tools/scrape_config_builder/README.md)
- **Helper Input Schema Docs**: Section "V0.1 Schema Details" in README
- **Function App YAML Interpreter**: [function_app/src/scraper.py](../function_app/src/scraper.py#L200) (search for `source_pages` array processing)

---

**Last Updated**: May 2026  
**Status**: v0.1 recommended for new datasets and archive-capable datasets; v2.0 still supported for backward compatibility
