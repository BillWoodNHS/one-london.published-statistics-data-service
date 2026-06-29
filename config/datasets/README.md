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
- optional: `excel_sheet` (name of the sheet/tab to read for `.xlsx`/`.xls`/`.ods` sources; defaults to the first sheet when omitted)
- optional: `sub_tables` (split one discovered source into multiple output tables — see below)
- optional: `unpivot` (reshape wide, repeating columns into a long format — see below)

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

## Sub-Tables (splitting one source into multiple output tables)

Sometimes a single discovered source doesn't map to a single output table:

- A `.zip` payload may bundle files with different schemas (e.g. a main data file plus a coverage/lookup file).
- A `.xlsx`/`.xls`/`.ods` workbook may have several tabs, some of which are formatted reports/summaries to ignore, and others — possibly more than one — containing distinct tabular data.

`sub_tables` handles both cases with the same mechanism: each entry is a rule that pulls part of a source out into its own output table, with its own `object_name_suffix`/`adls_path_prefix` (dbt provisions an `INGEST_<suffix>`/`RAW_<suffix>` pair per sub_table automatically). Each entry must define **exactly one** of `filename_patterns` or `sheet_name_patterns` — not both, not neither.

`object_name_suffix` must be unique across the **whole dataset file**, not just within one target — it is what dbt and the local DuckDB loader use to name the physical `INGEST_<suffix>`/`RAW_<suffix>` tables, with no `sub_dataset_id` qualifier. Reusing the same suffix across sibling targets (e.g. one per organism/region) silently merges their data into the same physical table.

Common fields:
- `object_name_suffix`: same naming rules as the target's own `object_name_suffix`.
- `adls_path_prefix`: same path rules as the target's own `adls_path_prefix`.

### Filename-routed (ZIP extraction)

- `filename_patterns`: a regex string, or list of regex strings, matched case-insensitively against the basename of each file extracted from the ZIP. The first sub_table with a matching pattern wins.
- A file that matches no `filename_patterns` across any sub_table falls through to the parent target's own `adls_path_prefix` — it is still ingested, just under the target's main table rather than a sub_table.

```yaml
sub_tables:
  - object_name_suffix: GP_APPTS_DAILY_COUNTS_COVERAGE
    adls_path_prefix: appointments-in-general-practice/daily-counts-coverage
    filename_patterns:
      - APPOINTMENTS_GP_COVERAGE
```

### Sheet-routed (Excel/ODS tab splitting)

- `sheet_name_patterns`: a regex string, or list of regex strings, matched case-insensitively against sheet/tab names in the workbook — any pattern in the list matching is enough. Use a list when wording varies across releases (e.g. some files say "national ... data", others say "national ... cases"). Every sheet that matches becomes its own output file, all routed to that sub_table — if several sheets match (e.g. one tab per month with the same schema), each produces a separate output but all land in the same sub_table's table.
- `start_cell` (optional): the top-left cell of the table, **including its header row** — e.g. `B5`. Rows above it are skipped and columns to its left are dropped. Defaults to `A1` when omitted.
- A sheet that matches no `sheet_name_patterns` across any sub_table on the target is **dropped, not ingested** — this is the point: non-matching tabs are presumed to be formatted reports/summaries, not data. This is deliberately different from the filename-routed fallback above, where an unmatched file still gets ingested under the parent target.
- If a target defines sheet-routed sub_tables but none of their patterns match any sheet in a given workbook, loading that source fails loudly (manifest/source mismatch) rather than silently producing no output.
- Prefer loose patterns (e.g. `raw.*data` rather than a literal `Table_2_raw_data`) — published tab names rarely match an assumed literal string exactly, and `re.search` already runs case-insensitively, so the pattern only needs to capture the meaningful words and their order.

```yaml
sub_tables:
  - object_name_suffix: WAITING_LIST_BY_TRUST
    adls_path_prefix: waiting-lists/by-trust
    sheet_name_patterns: ^Trust
  - object_name_suffix: WAITING_LIST_BY_ICB
    adls_path_prefix: waiting-lists/by-icb
    sheet_name_patterns:
      - national.*data
      - national.*cases
    start_cell: B3
```

Note: `sheet_name_patterns`/`start_cell` and the simple `excel_sheet` field address different needs — use `excel_sheet` when the whole workbook is one table that just happens not to be on the first tab; use sheet-routed `sub_tables` when the workbook contains multiple distinct tables across tabs.

## Unpivoting (reshaping wide, repeating columns into a long format)

Some sources name a column after each reporting period it covers (e.g. one
column per month: `Apr 2025`, `May 2025`, ...), or name a column after each
metric it reports (e.g. `Attendances`, `Admissions`, ...). Left as-is, these
columns accumulate over time — a new month column appears every release, and
a full backlog/historical load brings in years of distinct columns at once.
This causes permanent schema drift in the ingested table.

`unpivot` reshapes a wide table into a stable long format **before** it is
written to storage, so the ingested table's columns never grow. It is
generic — it has no notion of "dates" or "metrics", it simply melts every
column that isn't listed in `id_columns`:

- `id_columns`: the columns to keep as-is per output row. List the small,
  stable set of identifying columns (e.g. org code/name) — **not** the
  wide/repeating columns, which may be numerous and whose exact names can
  vary release to release (e.g. `Apr-25` one year, `April 2025` the next).
- `variable_column_name`: the output column that receives each melted
  column's original header text (e.g. `reporting_period`, or `metric` for
  a column-per-metric source).
- `value_column_name`: the output column that receives each melted
  column's cell value. Defaults to `value`.

No interpretation of the melted header text happens here (e.g. parsing
`Apr 2025` into a real date) — that is a downstream, dataset-specific
concern best handled in a dbt staging model.

`unpivot` can be set on a target (applies to the whole source) or on an
individual `sub_table` (applies to just that routed sheet/file) — use the
sub_table form when only one tab of a workbook is wide-format.

```yaml
sub_tables:
  - object_name_suffix: NATIONAL_DATA
    adls_path_prefix: cdi-monthly/national-data
    sheet_name_patterns:
      - Table_1_national_data
    start_cell: B4
    unpivot:
      id_columns:
        - Org Code
        - Org name
      variable_column_name: reporting_period
      value_column_name: value
```

A 12-column 2019 file and an 18-column 2026 file of the same series both
reduce to the same `id_columns` + `reporting_period` + `value` shape, so no
column list ever needs to be enumerated or updated as new periods appear.

## Authoring Rules

- Keep `sub_dataset_id` specific and stable.
- Keep `object_name_suffix` stable and concise; use uppercase letters, digits, and underscores only.
- Do not include Snowflake object prefixes in `object_name_suffix`; dbt prepends `STG_`, `PIPE_`, `INGEST_`, and `RAW_`.
- Keep `adls_path_prefix` stable; use only lowercase letters, digits, hyphens, underscores, and forward slashes — no leading/trailing slashes, no `..`.
- `adls_path_prefix` is a relative path within the shared ADLS container. The storage account and container are provided via the `adls_url_root` dbt variable.
- Use narrow `text_filter` patterns to avoid ambiguous links.
- Set `file_extensions` where possible (`csv`, `zip`, `xlsx`, `xls`).
- If manual fallback is required, configure `fallback.manual_drop_path` clearly.
- Keep `sub_tables` patterns (`filename_patterns` or `sheet_name_patterns`) narrow and non-overlapping with sibling sub_tables on the same target — overlapping patterns within the same routing dimension (filename vs. sheet name) are rejected at load time.
- Confirm `sheet_name_patterns`/`start_cell` against the real workbook before relying on them — sheet names and header positions in published spreadsheets can change between releases.
- When a source has one column per reporting period or per metric, configure `unpivot` rather than letting the column list grow unbounded — list `id_columns` (the small, stable set), not the wide/repeating columns.

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
