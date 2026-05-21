# Dataset Manifests

Each file in this folder declares how one supplier series is discovered and ingested.

## Manifest Shape

Required top-level keys:
- `dataset_id`
- `series_id`
- `entry_url`
- `publication_date`
- `targets`

`publication_date`:
- `source`: currently expected to be values like `link_text` or `url_segment`
- `pattern`: regex used to extract publication date token

Each entry in `targets`:
- `sub_dataset_id`: defines path isolation and downstream raw-table isolation
- `scrape_steps`: ordered chain of link extraction steps
- optional: `reporting_period_columns`

## Authoring Rules

- Keep `sub_dataset_id` specific and stable.
- Use narrow `text_filter` patterns to avoid ambiguous links.
- Set `file_extensions` where possible (`csv`, `zip`, `xlsx`, `xls`).
- If manual fallback is required, configure `fallback.manual_drop_path` clearly.

## Add New Series Checklist

1. Copy an existing manifest as a template.
2. Update identifiers and scrape path.
3. Confirm publication date regex matches real page text.
4. Run local tests.
5. Add or update fixtures in `tests/fixtures/manifests/` for coverage.
