# CI/CD Pipeline and Deployment

This project supports robust, secure, and environment-agnostic CI/CD for dbt/Snowflake deployments using both GitHub Actions and Azure DevOps. All pipeline logic is implemented in reusable PowerShell scripts under `tools/`.

## Pipeline Overview

- **Linting**: Runs pre-commit checks (black, flake8, isort) on all branches.
- **Testing**: Runs the full pytest suite (unit and integration) on all branches.
- **Deployment**: Runs `dbt run` and `dbt test` against Snowflake on the `main` branch only.

### Supported Environments
- **GitHub Actions**: See `.github/workflows/ci.yml` for configuration and required secrets.
- **Azure DevOps**: See `azure-pipelines.yml` for configuration and required variable groups.

## Secure Snowflake Authentication

The deployment supports both **password** and **key-pair** authentication for Snowflake. Key-pair authentication is recommended for production and CI/CD.

### Required Environment Variables/Secrets
- `SNOWFLAKE_ACCOUNT`       (e.g. xy12345.eu-west-2.aws)
- `SNOWFLAKE_USER`          (service account username)
- `SNOWFLAKE_ROLE`          (e.g. PSDS_DEPLOY_ROLE)
- `SNOWFLAKE_DATABASE`      (e.g. ONE_LONDON_PSDS)
- `SNOWFLAKE_WAREHOUSE`     (e.g. PSDS_WH)
- `SNOWFLAKE_SCHEMA`        (target schema)
- `SNOWFLAKE_PRIVATE_KEY`   (PEM-encoded private key, base64 or raw; **recommended**)
- `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` (optional, if key is encrypted)
- `SNOWFLAKE_PASSWORD`      (optional, fallback if key not set)

### How Authentication Works
- If `SNOWFLAKE_PRIVATE_KEY` is set, key-pair authentication is used.
- If not, falls back to `SNOWFLAKE_PASSWORD`.
- The script `tools/ci_render_profiles_yml.ps1` generates a secure `profiles.yml` for dbt at runtime.

## Pipeline Scripts

- `tools/ci_lint.ps1`: Runs pre-commit lint checks.
- `tools/ci_test.ps1`: Runs pytest suite (unit and integration).
- `tools/ci_dbt_deploy.ps1`: Installs dbt dependencies, renders `profiles.yml`, runs `dbt run` and `dbt test`, and cleans up credentials.
- `tools/ci_render_profiles_yml.ps1`: Renders a secure `profiles.yml` for dbt, supporting both key-pair and password auth.

## Usage in Pipelines

- **GitHub Actions**: Secrets are set in repository settings. See `.github/workflows/ci.yml` for job steps.
- **Azure DevOps**: Variables are set in a variable group (e.g., `psds-snowflake`). See `azure-pipelines.yml` for job steps.

## Local Testing of Deployment

You can test the deployment scripts locally by setting the required environment variables and running:

```powershell
$env:SNOWFLAKE_ACCOUNT = '...'
$env:SNOWFLAKE_USER = '...'
# ...set all required variables...
./tools/ci_dbt_deploy.ps1
```

## Security Notes
- Credentials are never stored in the repository.
- The `profiles.yml` is generated at runtime and deleted after use.
- Use repository/variable group secrets for all sensitive values.

## References
- [dbt Snowflake Auth Docs](https://docs.getdbt.com/reference/warehouse-profiles/snowflake-profile)
- [Snowflake Key Pair Auth](https://docs.snowflake.com/en/user-guide/key-pair-auth)
