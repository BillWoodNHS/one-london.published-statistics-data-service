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

Optional `subject_period`:
- `source`: values like `link_text` or `url_segment`
- `pattern`: regex used to extract the period the data describes (for example `March 2026`)

Each entry in `targets`:
- `sub_dataset_id`: defines path isolation and downstream raw-table isolation
- `object_name_suffix`: explicit Snowflake naming suffix consumed by dbt provisioning
- `adls_path_prefix`: explicit relative ADLS sub-folder path for file storage (e.g. `appointments-in-general-practice/practice-level`)
- `scrape_steps`: ordered chain of link extraction steps
- optional: `reporting_period_columns`
- optional: `page_date_selectors` (regex patterns to extract page-level publication/revision date per sub-publication)
- optional: `period_coverage` (hint block to prioritize runtime period-range detection)

`period_coverage` options:
- `file_scope.duration_type`: `unknown` | `single_period` | `rolling` | `calendar_ytd` | `fiscal_ytd` | `daily`
- `file_scope.duration_value`: integer or `null` (for patterns like rolling N)
- `file_scope.duration_unit`: `day` | `month` | `quarter` | `year` | `null`
- `file_scope.fiscal_year_start_month`: integer `1`-`12` or `null`
- `breakdown_granularity`: ordered list from `day`, `month`, `quarter`, `year`

Recommended default:

```yaml
period_coverage:
	file_scope:
		duration_type: unknown
		duration_value: null
		duration_unit: null
		fiscal_year_start_month: 4
	breakdown_granularity:
		- month
```

## Authoring Rules

- Keep `sub_dataset_id` specific and stable.
- Keep `object_name_suffix` stable and concise; use uppercase letters, digits, and underscores only.
- Do not include Snowflake object prefixes in `object_name_suffix`; dbt prepends `STG_`, `PIPE_`, `INGEST_`, and `RAW_`.
- Keep `adls_path_prefix` stable; use only lowercase letters, digits, hyphens, underscores, and forward slashes — no leading/trailing slashes, no `..`.
- `adls_path_prefix` is a relative path within the shared ADLS container. The storage account and container are provided via the `adls_url_root` dbt variable.
- Use narrow `text_filter` patterns to avoid ambiguous links.
- Set `file_extensions` where possible (`csv`, `zip`, `xlsx`, `xls`).
- If manual fallback is required, configure `fallback.manual_drop_path` clearly.

## Add New Series Checklist

1. Copy an existing manifest as a template.
2. Update identifiers and scrape path.
3. Confirm publication date regex matches real page text.
4. Run local tests.
5. Add or update fixtures in `tests/fixtures/manifests/` for coverage.

## June 2026 Contract Update

- Storage paths now partition by download time (`download_year`, `download_month`, `downloaded_at`) rather than `subject_period`.
- Sidecar metadata now stores `_SUBJECT_PERIOD_FROM` and `_SUBJECT_PERIOD_TO` (inclusive timestamps), plus file scope and granularity diagnostics.
- Target configs may include optional `period_coverage` hints to prioritize runtime period inference.
