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
5. Attempt manual fallback where configured and needed.

## Adding Support for New File Patterns

If a new source format is needed:
1. Extend normalization logic in `src/download_and_normalize.py`.
2. Keep output contract as CSV bytes and deterministic metadata.
3. Add tests in `tests/` to prove behavior.
