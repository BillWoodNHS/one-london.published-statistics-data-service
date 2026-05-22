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

$settingsPath = [Environment]::GetEnvironmentVariable("DBT_DEPLOYMENT_SETTINGS_PATH")
if (-not $settingsPath) {
    $settingsPath = Join-Path $PSScriptRoot ".." "config" "dbt" "deployment.settings.json"
}

$settings = $null
if (Test-Path $settingsPath) {
    $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
    Write-Host "Loaded dbt deployment settings from $settingsPath"
}

function Set-EnvIfMissing([string]$name, [string]$value) {
    if (-not [Environment]::GetEnvironmentVariable($name) -and $value) {
        [Environment]::SetEnvironmentVariable($name, $value)
    }
}

if ($settings -and $settings.snowflake) {
    Set-EnvIfMissing "SNOWFLAKE_ROLE" $settings.snowflake.role
    Set-EnvIfMissing "SNOWFLAKE_DATABASE" $settings.snowflake.database
    Set-EnvIfMissing "SNOWFLAKE_WAREHOUSE" $settings.snowflake.warehouse
    Set-EnvIfMissing "SNOWFLAKE_SCHEMA" $settings.snowflake.schema
}

$requiredVars = @(
    "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER",
    "SNOWFLAKE_ROLE", "SNOWFLAKE_DATABASE", "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_SCHEMA"
)
foreach ($var in $requiredVars) {
    if (-not [Environment]::GetEnvironmentVariable($var)) {
        Write-Error "Required environment variable '$var' is not set."
        exit 1
    }
}

$hasPrivateKey = [Environment]::GetEnvironmentVariable("SNOWFLAKE_PRIVATE_KEY")
$hasPassword = [Environment]::GetEnvironmentVariable("SNOWFLAKE_PASSWORD")
if (-not $hasPrivateKey -and -not $hasPassword) {
    Write-Error "Set SNOWFLAKE_PRIVATE_KEY (preferred) or SNOWFLAKE_PASSWORD for dbt deployment authentication."
    exit 1
}

$dbtVars = @{}
if ($settings -and $settings.dbt_vars) {
    $settings.dbt_vars.PSObject.Properties | ForEach-Object {
        $dbtVars[$_.Name] = $_.Value
    }
}

$dbtVarsJson = "{}"
if ($dbtVars.Count -gt 0) {
    $dbtVarsJson = $dbtVars | ConvertTo-Json -Compress
}

$authMode = if ($hasPrivateKey) { "private_key" } else { "password" }
$effectiveConfig = [ordered]@{
    settings_path = $settingsPath
    settings_file_found = [bool](Test-Path $settingsPath)
    auth_mode = $authMode
    snowflake_account = [Environment]::GetEnvironmentVariable("SNOWFLAKE_ACCOUNT")
    snowflake_user = [Environment]::GetEnvironmentVariable("SNOWFLAKE_USER")
    snowflake_role = [Environment]::GetEnvironmentVariable("SNOWFLAKE_ROLE")
    snowflake_database = [Environment]::GetEnvironmentVariable("SNOWFLAKE_DATABASE")
    snowflake_warehouse = [Environment]::GetEnvironmentVariable("SNOWFLAKE_WAREHOUSE")
    snowflake_schema = [Environment]::GetEnvironmentVariable("SNOWFLAKE_SCHEMA")
    dbt_target = "prod"
    dbt_vars = $dbtVars
}

Write-Host "=== Effective dbt deployment configuration ==="
($effectiveConfig | ConvertTo-Json -Depth 8) | Write-Host

$dbtDir = Join-Path $PSScriptRoot ".." "dbt"
Push-Location $dbtDir

try {
    # Write a profiles.yml using key-pair or password auth
    & (Join-Path $PSScriptRoot 'ci_render_profiles_yml.ps1')
    if ($LASTEXITCODE -ne 0) { throw "profiles.yml rendering failed" }

    Write-Host "=== Installing dbt dependencies ==="
    dbt deps
    if ($LASTEXITCODE -ne 0) { throw "dbt deps failed" }

    Write-Host "=== Running dbt models ==="
    dbt run --target prod --vars "$dbtVarsJson"
    if ($LASTEXITCODE -ne 0) { throw "dbt run failed" }

    Write-Host "=== Provisioning telemetry ingestion objects ==="
    dbt run-operation provision_telemetry_pipeline --target prod --args "{}" --vars "$dbtVarsJson"
    if ($LASTEXITCODE -ne 0) { throw "telemetry provisioning failed" }

    Write-Host "=== Running dbt tests ==="
    dbt test --target prod --vars "$dbtVarsJson"
    if ($LASTEXITCODE -ne 0) { throw "dbt test failed" }

    Write-Host "=== dbt deployment complete ==="
} finally {
    Pop-Location
    # Remove profiles.yml so credentials don't linger on the agent
    $profilePath = Join-Path $HOME ".dbt" "profiles.yml"
    if (Test-Path $profilePath) { Remove-Item $profilePath -Force }
}
