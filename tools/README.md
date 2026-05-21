# Tools

This folder contains developer utility scripts.


## Contents

- `init_dev_environment.ps1`: Creates/updates local virtual environment and installs dependencies.
- `run_local_e2e.py`: Local e2e orchestrator using local storage mode.
- `run_local_e2e.ps1`: PowerShell wrapper for local e2e run.
- `ci_lint.ps1`: Runs pre-commit lint checks using Ruff (used in CI/CD).
- `ci_test.ps1`: Runs pytest suite (unit and integration; used in CI/CD).
- `ci_dbt_deploy.ps1`: Installs dbt dependencies, renders `profiles.yml`, runs `dbt run` and `dbt test`, and cleans up credentials (used in CI/CD).
- `ci_render_profiles_yml.ps1`: Renders a secure `profiles.yml` for dbt, supporting both key-pair and password auth (used in CI/CD).


## Usage

### Local Development

- Initialize environment:
	```powershell
	./tools/init_dev_environment.ps1
	```
- Recreate virtual environment:
	```powershell
	./tools/init_dev_environment.ps1 -RecreateVenv
	```
- Run local e2e flow:
	```powershell
	./tools/run_local_e2e.ps1
	```

### CI/CD and Secure Snowflake Auth

- The CI/CD scripts are called by both GitHub Actions and Azure DevOps pipelines.
- `ci_dbt_deploy.ps1` and `ci_render_profiles_yml.ps1` support both password and key-pair authentication for Snowflake.
- Set the following environment variables (see docs/CI-CD.md for details):
	- `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_ROLE`, `SNOWFLAKE_DATABASE`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_SCHEMA`
	- `SNOWFLAKE_PRIVATE_KEY` (recommended) and optional `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE`, or `SNOWFLAKE_PASSWORD` as fallback
- Credentials are never stored in the repo; `profiles.yml` is generated at runtime and deleted after use.


## Extending Tooling

When adding new scripts:
1. Keep scripts idempotent where possible.
2. Document required environment variables and security considerations.
3. Add usage examples here and update this README.
