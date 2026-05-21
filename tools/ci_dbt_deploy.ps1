<#
.SYNOPSIS
    Deploy dbt models to Snowflake.
    Requires environment variables for Snowflake credentials (set by pipeline or locally).
    Called by both GitHub Actions and Azure DevOps pipelines.

Required environment variables:
    SNOWFLAKE_ACCOUNT       - e.g. xy12345.eu-west-2.aws
    SNOWFLAKE_USER          - service account username
    SNOWFLAKE_PASSWORD      - service account password (or use key pair)
    SNOWFLAKE_ROLE          - e.g. PSDS_DEPLOY_ROLE
    SNOWFLAKE_DATABASE      - e.g. ONE_LONDON_PSDS
    SNOWFLAKE_WAREHOUSE     - e.g. PSDS_WH
    SNOWFLAKE_SCHEMA        - target schema, e.g. PRESENTATION
#>
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$requiredVars = @(
    "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD",
    "SNOWFLAKE_ROLE", "SNOWFLAKE_DATABASE", "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_SCHEMA"
)
foreach ($var in $requiredVars) {
    if (-not [Environment]::GetEnvironmentVariable($var)) {
        Write-Error "Required environment variable '$var' is not set."
        exit 1
    }
}

$dbtDir = Join-Path $PSScriptRoot ".." "dbt"
Push-Location $dbtDir

try {
one_london_psds:

        # Write a profiles.yml using key-pair or password auth
        & (Join-Path $PSScriptRoot 'ci_render_profiles_yml.ps1')
        if ($LASTEXITCODE -ne 0) { throw "profiles.yml rendering failed" }

    Write-Host "=== Installing dbt dependencies ==="
    dbt deps
    if ($LASTEXITCODE -ne 0) { throw "dbt deps failed" }

    Write-Host "=== Running dbt models ==="
    dbt run --target prod
    if ($LASTEXITCODE -ne 0) { throw "dbt run failed" }

    Write-Host "=== Running dbt tests ==="
    dbt test --target prod
    if ($LASTEXITCODE -ne 0) { throw "dbt test failed" }

    Write-Host "=== dbt deployment complete ==="
} finally {
    Pop-Location
    # Remove profiles.yml so credentials don't linger on the agent
    $profilePath = Join-Path $HOME ".dbt" "profiles.yml"
    if (Test-Path $profilePath) { Remove-Item $profilePath -Force }
}
