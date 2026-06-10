# Function App

This folder contains the Azure Functions ingestion runtime.

## Contents

- `function_app.py`: Timer trigger entrypoint.
- `src/`: Runtime modules for manifest loading, scraping, normalization, storage IO, and orchestration.
- `requirements.txt`: Runtime dependencies.
- `local.settings.sample.json`: Example local environment settings.

## Runtime Flow

1. Load manifests.
2. Discover links via scrape-step chains.
3. Download and normalize payload to CSV.
4. Write CSV and metadata sidecar to storage path.
5. Emit telemetry events as JSONL to the telemetry prefix.
6. Attempt manual fallback where configured and needed.

## Telemetry

Ingestion telemetry is written to ADLS as JSONL under the prefix configured by
`TELEMETRY_PREFIX` (default `_telemetry/function_app_events`).

Each event contains operational fields including stage, status, attempt_number,
source metadata, and row-count metrics where available.

## Adding Support for New File Patterns

If a new source format is needed:
1. Extend normalization logic in `src/download_and_normalize.py`.
2. Keep output contract as CSV bytes and deterministic metadata.
3. Add tests in `tests/` to prove behavior.

## June 2026 Contract Update

- Storage paths now partition by download time (`download_year`, `download_month`, `downloaded_at`) rather than `subject_period`.
- Sidecar metadata now stores `_SUBJECT_PERIOD_FROM` and `_SUBJECT_PERIOD_TO` (inclusive timestamps) plus inference diagnostics.
- Target configs may include optional `period_coverage` hints to prioritize runtime period inference.
