# Claude Code Rules

## General Principles
- Follow SOLID principles at all times
- Prefer composition over inheritance
- Write self-documenting code; avoid unnecessary comments
- Functions should do one thing and be under 20 lines
- Keep abstraction levels consistent within a function — do not mix high-level
  logic with low-level detail

## Naming
- Use descriptive, intention-revealing names
- Avoid abbreviations (use `user_account`, not `usr_acc`)
- Boolean variables should read as questions: `is_loading`, `has_error`
- dbt models: use `snake_case`; prefix staging models with `stg_`,
  intermediates with `int_`, marts with `fct_` or `dim_`

## Functions & Methods
- Maximum 3 function parameters; use a dataclass or TypedDict beyond that
- No side effects in pure functions
- Always handle errors explicitly — no silent catches
- No boolean/flag parameters — split into two functions instead
- No output arguments — return values, do not mutate parameters passed in
- Type hints are required on all function signatures

## Classes & Structure
- Classes should have a single reason to change
- Keep classes under 100 lines; split if they grow beyond this
- Avoid "God objects" that know too much or do too much
- Use dependency injection; never instantiate dependencies inside a function
  or class
- Use Pydantic for data validation and schema definition; avoid raw dict access

## Code Style
- No magic numbers; extract to named constants
- Avoid deeply nested conditionals — use early returns
- DRY: if logic is duplicated twice, extract it
- No deeply nested callbacks — extract or use async/await

## Comments
- If code requires a comment to be understood, rewrite the code instead
- TODOs must include a ticket reference (e.g. `# TODO: #123`)
- No commented-out code in commits

## Linting (Ruff)
- All code must comply with Ruff's default ruleset
- Maximum line length is 88 characters — no exceptions
- If a line exceeds 88 characters, restructure it: break expressions across
  lines, extract variables, or split function arguments — do not disable
  the rule with `# noqa`

## dbt — General
- Prefer dbt-native solutions (tests, macros, materializations, snapshots)
  over Python workarounds
- Jinja logic belongs in macros, not inline in models; inline Jinja should
  only be used for simple `ref()`, `source()`, or `config()` calls
- Use generic tests before singular tests; only use singular tests when a
  generic test cannot cover the requirement
- No `SELECT *` in models; always use explicit column lists
- Use CTEs in preference to subqueries; structure models as a sequence of
  named CTEs with a final simple SELECT
- All models must have a description in the `.yml` schema file
- All source tables must be declared in a `sources:` block

## dbt — Adapter Semantics (Snowflake / DuckDB)
- This project runs against two targets: DuckDB (local dev/test) and
  Snowflake (production)
- Write adapter-agnostic SQL by default; use `{{ adapter.dispatch() }}` or
  `{% if target.type == 'duckdb' %}` guards only when a genuine
  incompatibility exists
- Do not add Python or DuckDB-native Python logic to dbt tests simply because
  it is easier locally — exhaust adapter-agnostic SQL options first
- Python fallbacks in tests are acceptable only when the logic genuinely
  cannot be expressed in SQL that runs on both targets; document why with
  a comment
- Known Snowflake-specific syntax that must be macro-wrapped or guarded:
  `QUALIFY`, `FLATTEN`, `LATERAL FLATTEN`, `VARIANT`/`PARSE_JSON`,
  `ARRAY_AGG` with ordering, `ILIKE`
- When writing a new macro or test, verify it executes cleanly against
  DuckDB before assuming Snowflake compatibility

## SQL Style
- All SQL keywords in uppercase (`SELECT`, `FROM`, `WHERE`, `JOIN`)
- Explicit `JOIN` type always specified (never bare `JOIN`; use `INNER JOIN`)
- Table aliases must be meaningful, not single letters
- Aggregations and window functions should be extracted into a prior CTE
  rather than nested inline

## Testing
- Every new Python function must have a corresponding unit test
- Tests should follow the Arrange-Act-Assert pattern
- Tests must be independent — no shared mutable state between tests
- No logic in tests (no `if`/`for` in test bodies)
- For dbt, prefer schema tests (`.yml`) for column-level assertions and
  singular tests (`.sql`) only for multi-model or complex logic
- No commented-out code in commits