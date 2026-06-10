# GitHub Workflows

This folder contains GitHub Actions workflows for CI and optional deployment.

## Current Workflows

- `ci.yml`: Runs lint and tests on push/PR. Contains a deploy job for dbt that is disabled by default.

## Deployment Toggle

The deploy job in `ci.yml` only runs when both conditions are true:

1. Branch is `main`
2. Repository variable `ENABLE_GITHUB_DEPLOY` is set to `true`

Condition used in workflow:

```yaml
if: ${{ github.ref == 'refs/heads/main' && vars.ENABLE_GITHUB_DEPLOY == 'true' }}
```

## How To Enable Deployment

1. Go to GitHub repository settings.
2. Open **Settings -> Secrets and variables -> Actions -> Variables**.
3. Create repository variable:
   - Name: `ENABLE_GITHUB_DEPLOY`
   - Value: `true`
4. Trigger a run on `main`.

## How To Keep Deployment Disabled

- Do not create `ENABLE_GITHUB_DEPLOY`, or set it to any value other than `true`.
- Lint and test jobs still run normally.

## Notes

- Deployment code remains in source control and can be enabled without code changes.
- Required Snowflake secrets must be configured before enabling deployment.

## June 2026 Contract Update

- Storage paths now partition by download time (`download_year`, `download_month`, `downloaded_at`) rather than `subject_period`.
- Sidecar metadata now stores `_SUBJECT_PERIOD_FROM` and `_SUBJECT_PERIOD_TO` (inclusive timestamps) plus inference diagnostics.
- Target configs may include optional `period_coverage` hints to prioritize runtime period inference.
