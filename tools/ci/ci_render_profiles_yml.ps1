<#
.SYNOPSIS
    Render dbt profiles.yml for Snowflake, supporting key-pair or password auth.
    Called by both CI/CD pipelines before dbt run.

Required environment variables:
    SNOWFLAKE_ACCOUNT       - e.g. xy12345.eu-west-2.aws
    SNOWFLAKE_USER          - service account username
    SNOWFLAKE_ROLE          - e.g. PSDS_DEPLOY_ROLE
    SNOWFLAKE_DATABASE      - e.g. ONE_LONDON_PSDS
    SNOWFLAKE_WAREHOUSE     - e.g. PSDS_WH
    SNOWFLAKE_SCHEMA        - target schema, e.g. PRESENTATION
    SNOWFLAKE_PRIVATE_KEY   - (optional) PEM-encoded private key (base64 or raw)
    SNOWFLAKE_PRIVATE_KEY_PASSPHRASE - (optional) passphrase for private key
    SNOWFLAKE_PASSWORD      - (optional) fallback if key not set
#>
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$profilesDir = Join-Path $HOME ".dbt"
New-Item -ItemType Directory -Force -Path $profilesDir | Out-Null

$account = $env:SNOWFLAKE_ACCOUNT
$user = $env:SNOWFLAKE_USER
$role = $env:SNOWFLAKE_ROLE
$database = $env:SNOWFLAKE_DATABASE
$warehouse = $env:SNOWFLAKE_WAREHOUSE
$schema = $env:SNOWFLAKE_SCHEMA

# Prefer key-pair auth if SNOWFLAKE_PRIVATE_KEY is set
$privateKey = $env:SNOWFLAKE_PRIVATE_KEY
$privateKeyPassphrase = $env:SNOWFLAKE_PRIVATE_KEY_PASSPHRASE
$password = $env:SNOWFLAKE_PASSWORD

if ($privateKey) {
    Write-Host "Rendering profiles.yml for key-pair authentication."
    $keySection = "private_key_path: /tmp/snowflake_key.pem"
    if ($privateKeyPassphrase) {
        $keySection += "\n      private_key_passphrase: $privateKeyPassphrase"
    }
    $profileContent = @"
one_london_psds:
  target: prod
  outputs:
    prod:
      type: snowflake
      account: $account
      user: $user
      role: $role
      database: $database
      warehouse: $warehouse
      schema: $schema
      threads: 4
      client_session_keep_alive: false
      $keySection
"@
    # Write the private key to a temp file
    $keyPath = "/tmp/snowflake_key.pem"
    if ($IsWindows) { $keyPath = "$env:TEMP\snowflake_key.pem" }
    $privateKey | Set-Content -Path $keyPath -Encoding ascii
} elseif ($password) {
    Write-Host "Rendering profiles.yml for password authentication."
    $profileContent = @"
one_london_psds:
  target: prod
  outputs:
    prod:
      type: snowflake
      account: $account
      user: $user
      password: $password
      role: $role
      database: $database
      warehouse: $warehouse
      schema: $schema
      threads: 4
      client_session_keep_alive: false
"@
} else {
    Write-Error "Neither SNOWFLAKE_PRIVATE_KEY nor SNOWFLAKE_PASSWORD is set."
    exit 1
}

$profileContent | Set-Content (Join-Path $profilesDir "profiles.yml") -Encoding UTF8
