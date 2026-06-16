# Function App: V0.1 YAML Interpretation Guide

**Purpose**: Explain how the function app's file discovery engine interprets and executes v0.1 YAML configs with multi-page discovery and sibling page traversal.

---

## Architecture Overview

### Components

1. **Helper Tool** (`tools/scrape_config_builder/scrape-config-helper.py`):
   - Reads v0.1 JSON helper input specs
   - Generates v0.1 YAML configs with `source_pages` array and `sibling_discovery` config
   - Validates patterns against live web pages (no file download)

2. **Manifest Loader** (`function_app/src/manifest_loader.py`):
   - Parses YAML config files into Python dataclass models
   - Validates structure and required fields
   - Supports both v2.0 (legacy) and v0.1 (new) YAML formats

3. **Scraper** (`function_app/src/scraper.py`):
   - Executes file discovery using loaded configs
   - Processes `source_pages` array per target
   - Implements sibling page discovery with configurable limits
   - Deduplicates results across all source pages

4. **DBT Models** (`dbt/models/`):
   - Ingest scraped files into data warehouse
   - Unchanged by v0.1 YAML (full backward compatibility)

---

## V0.1 YAML Structure

### Complete Example

```yaml
dataset_id: example-dataset
series_id: example-dataset
entry_url: https://example.org/datasets/example

publication_date:
  source: link_text
  pattern: (published|date):\s*(\d{1,2}\s+\w+\s+\d{4})

subject_period:
  rules:
    - source: file_name
      pattern: (jan|feb|mar)[-_](\d{4})
    - source: url_segment
      pattern: (jan|feb|mar)[-_](\d{4})
    - source: page_text
      pattern: (jan|feb|mar)[-_](\d{4})

fallback:
  allow_manual_acquisition: true
  manual_drop_path: manual/example-dataset
  max_auto_retries: 3
  timeout_threshold_minutes: 5

targets:
  - sub_dataset_id: monthly-data
    source_pages:
      - page_url: https://example.org/datasets/example
        page_role: default                           # ← Page's lifecycle role
        partitioning_strategy: none                   # ← How files are organized
        scrape_steps:
          - link_selector: a[href$='.csv']
            text_filter: data.*csv
            file_extensions: [csv]
        sibling_discovery:                           # ← Archive/multi-page discovery
          enabled: false
          link_selector: a[href]
          url_pattern: null
          text_pattern: null
          max_pages: 25
      - page_url: https://example.org/datasets/example/archive
        page_role: archive                           # ← Different role
        partitioning_strategy: subject_period        # ← Files split by period
        scrape_steps:
          - link_selector: a[href$='.csv']
            text_filter: data.*csv
            file_extensions: [csv]
        sibling_discovery:
          enabled: true                              # ← Enable auto-discovery
          link_selector: a[href]
          url_pattern: (jan|feb|mar)[-_](\d{4})     # ← Find month-year pages
          text_pattern: (FY|Q)\s*\d{4}               # ← Find "FY 2025" links
          max_pages: 25
    reporting_period_columns: []
    page_date_selectors:
      - (?:published|date):\s*(\d{1,2}\s+\w+\s+\d{4})
```

### Field Meanings

#### `source_pages` Array
Each element describes a distinct page context where files may appear.

**`page_role`** — Describes the page's purpose and lifecycle:
- `default`: Primary/landing page; expected to have current-period files
- `archive`: Historical/previous-period files grouped by time
- `sub_dataset_dedicated`: Page dedicated to single sub-dataset; cross-dataset discovery should not apply
- `subject_period_index`: Navigational index (e.g., FY links); not expected to have direct file downloads

**`partitioning_strategy`** — How files are organized on the page:
- `none`: All files on single page, no time-based partitioning
- `subject_period`: Files split into separate pages by month/year/quarter; siblings should be discovered
- `pagination`: Files paginated within single time period (e.g., "next page" button)
- `mixed`: Both pagination and subject-period partitioning

#### `sibling_discovery` Config
Controls automatic page traversal to find related pages.

```yaml
sibling_discovery:
  enabled: true|false                          # Enable automatic discovery?
  link_selector: a[href]                        # CSS selector for candidate links
  url_pattern: (jan|feb)[-_](\d{4})|null       # Regex to filter URLs; null = no filter
  text_pattern: (FY|Q)\s*\d{4}|null            # Regex to filter link text; null = no filter
  max_pages: 25                                 # Max sibling pages to visit
```

---

## Scraper Execution Flow

### High-Level Algorithm

```
for each target in config.targets:
    for each source_page in target.source_pages:
        files_from_this_page = discover_from_page(source_page)
        all_files.extend(files_from_this_page)

deduplicated_files = dedup(all_files by sub_dataset_id, canonical_url)
return deduplicated_files
```

### Detailed `discover_from_page()` Function

**Input**: `source_page` (one element from `source_pages[]` array)

**Steps**:

#### 1. Fetch Page
```python
response = requests.get(source_page.page_url)
page_html = response.text
```

#### 2. Apply Scrape Steps (to seed page)
```python
soup = BeautifulSoup(page_html)
candidate_links = soup.select(scrape_step.link_selector)  # CSS selector
files = []

for link in candidate_links:
    href = link.get('href')
    text = link.get_text()
    
    # Apply filters
    if not re.search(scrape_step.text_filter, text):
        continue  # Text doesn't match
    if not href.lower().endswith(tuple(scrape_step.file_extensions)):
        continue  # Extension doesn't match
    
    files.append(href)  # ← File URL from seed page
```

#### 3. Sibling Discovery (if enabled)
```python
if source_page.sibling_discovery.enabled:
    candidate_siblings = soup.select(
        source_page.sibling_discovery.link_selector
    )
    visited_siblings = 0
    
    for sibling_link in candidate_siblings:
        if visited_siblings >= source_page.sibling_discovery.max_pages:
            break
        
        sibling_url = sibling_link.get('href')
        sibling_text = sibling_link.get_text()
        
        # Filter by URL pattern
        if source_page.sibling_discovery.url_pattern:
            if not re.search(source_page.sibling_discovery.url_pattern, sibling_url):
                continue
        
        # Filter by link text pattern
        if source_page.sibling_discovery.text_pattern:
            if not re.search(source_page.sibling_discovery.text_pattern, sibling_text):
                continue
        
        # Visit sibling page and re-apply scrape steps
        sibling_response = requests.get(sibling_url)
        sibling_html = sibling_response.text
        sibling_soup = BeautifulSoup(sibling_html)
        
        sibling_links = sibling_soup.select(scrape_step.link_selector)
        for link in sibling_links:
            href = link.get('href')
            text = link.get_text()
            
            if re.search(scrape_step.text_filter, text) and \
               href.lower().endswith(tuple(scrape_step.file_extensions)):
                files.append(href)  # ← File URL from sibling page
        
        visited_siblings += 1
```

#### 4. Return Files from All Visited Pages
```python
return files  # Includes seed page + all visited sibling pages
```

### Deduplication

After all `source_pages` are processed:

```python
def deduplicate_files(files):
    seen = set()
    unique_files = []
    
    for file_url in files:
        # Normalize URL: strip, rstrip '/', lowercase scheme
        canonical = file_url.strip().rstrip('/').lower()
        
        # Deduplicate key: (sub_dataset_id, canonical_url)
        key = (target.sub_dataset_id, canonical)
        
        if key not in seen:
            seen.add(key)
            unique_files.append(file_url)
    
    return unique_files
```

---

## Real Example: DQMI File Discovery

### Scenario

**Dataset**: `data-quality-maturity-index`  
**Target**: `with-did`  
**Goal**: Find all monthly DID CSV files from current month + previous months

### YAML Config

```yaml
targets:
  - sub_dataset_id: with-did
    source_pages:
      # Page 1: Entry page (current month)
      - page_url: https://digital.nhs.uk/.../data-quality
        page_role: default
        partitioning_strategy: none
        scrape_steps:
          - link_selector: a[href*='did'], a[href*='DID']
            text_filter: DQMI.*CSV.*DID
            file_extensions: [csv]
        sibling_discovery:
          enabled: false
      
      # Page 2: Archive page (previous months with sibling discovery)
      - page_url: https://digital.nhs.uk/.../data-quality/archive
        page_role: archive
        partitioning_strategy: subject_period
        scrape_steps:
          - link_selector: a[href*='did'], a[href*='DID']
            text_filter: DQMI.*CSV.*DID
            file_extensions: [csv]
        sibling_discovery:
          enabled: true
          link_selector: a[href]
          url_pattern: (jan|feb|mar|...|dec)[-_]?(2024|2025|2026)
          text_pattern: (FY|Q|Month)
          max_pages: 25
```

### Execution Steps

**Phase 1: Visit Entry Page**
```
URL: https://digital.nhs.uk/.../data-quality
Selector: a[href*='did']
Filter: DQMI.*CSV.*DID
Result: [dqmi_99_csv-v2-did.csv]  ← Current month
Sibling discovery: OFF (enabled: false)
```

**Phase 2: Visit Archive Page**
```
URL: https://digital.nhs.uk/.../data-quality/archive
Selector: a[href*='did']
Filter: DQMI.*CSV.*DID
Result: [dqmi_98_csv-v2-did.csv]  ← Previous month on same page

Sibling discovery: ON (enabled: true)
  - Find all <a href> on page
  - Filter by URL pattern: (jan|feb|...|dec)[-_]?(2024|2025|2026)
  - Matched siblings:
    - /archive/2026-march → Visit & scrape
    - /archive/2026-february → Visit & scrape
    - /archive/2026-january → Visit & scrape
    - ...
    - /archive/2025-march → Visit & scrape
  - Re-apply scrape steps to each sibling page
  - Result from siblings: [dqmi_97_csv_v3_did.csv, ..., dqmi_80_csv_v1_did.csv]
```

**Phase 3: Deduplicate**
```
Files from entry page: 1
Files from archive page directly: 1
Files from archive sibling pages: 15
Deduplicated (by canonical URL): 17 total files
```

**Result**: **17 files** discovered from both entry page and archive page with automatic month-year sibling discovery.

---

## Legacy Support: v2.0 YAML

The scraper maintains backward compatibility with v2.0 YAML (single `scrape_steps` without `source_pages`):

```yaml
# v2.0 (legacy)
targets:
  - sub_dataset_id: monthly
    scrape_steps:
      - link_selector: a[href$='.csv']
        text_filter: monthly
        file_extensions: [csv]
```

**Normalization**: v2.0 is internally converted to v0.1-like structure:
- Create single-element `source_pages` array
- Set `page_role: default`
- Set `partitioning_strategy: none`
- Set `sibling_discovery.enabled: false`

**Result**: v2.0 configs still load, but v0.1 remains the active authoring standard.

---

## Performance Considerations

### Timeout and Limits

- **Per-request timeout**: Configurable via `fallback.timeout_threshold_minutes` (default: 5 min)
- **Max sibling pages**: Configurable via `sibling_discovery.max_pages` (default: 25)
- **Total discovery time**: Sum of all HTTP requests across all pages

### Optimization Tips

1. **Narrow URL pattern**: Use specific regex (e.g., `2025-26` not `20\d{2}`)
2. **Limit max_pages**: Reduce from 25 to 10-15 if dataset has many old archives
3. **Avoid generic selectors**: Use `a[href*='specific-token']` instead of `a[href]`
4. **Cache pages**: Scraper caches responses within single run; multiple source_pages on same URL re-use response

---

## Debugging

### Enable Logging

Set environment variable:
```bash
export LOG_LEVEL=DEBUG
```

### Common Issues

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| No files found from archive page | CSS selector doesn't match archive page structure | Test selector on live page; update `link_selector` in YAML |
| Sibling discovery finds wrong pages | URL pattern too loose | Tighten regex pattern; reduce `max_pages` |
| Timeout | Too many sibling pages visited | Reduce `max_pages`; narrow URL pattern |
| Duplicate files | Not deduplicated | Check canonical URL normalization logic |

---

## Future Enhancements

**Planned (Not Yet Implemented)**:
1. Conditional sibling discovery based on page status (new vs. stale)
2. Intelligent pagination detection (auto-follow "next" links)
3. Subject-period-aware caching across runs
4. Recursive sibling discovery (siblings of siblings)

---

## Related Documentation

- **Helper README**: [tools/scrape_config_builder/README.md](../../tools/scrape_config_builder/README.md)
- **Schema Migration Guide (Archived)**: [legacy/SCHEMA_MIGRATION_GUIDE_v2_to_v0p1.md](../legacy/SCHEMA_MIGRATION_GUIDE_v2_to_v0p1.md)
- **Scraper Implementation**: [function_app/src/scraper.py](../../function_app/src/scraper.py)
- **Manifest Loader**: [function_app/src/manifest_loader.py](../../function_app/src/manifest_loader.py)
- **Data Models**: [function_app/src/models.py](../../function_app/src/models.py)

---

**Last Updated**: May 2026  
**Version**: v0.1 YAML schema  
**Stability**: Stable; used in production for 11 datasets
