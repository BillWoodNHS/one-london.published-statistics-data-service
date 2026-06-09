<#
.SYNOPSIS
    Run the test suite via the unified runner (tools/local_dev/run_test_suite.py).
    Defaults to both python and duckdb suites. Produces JUnit XML in .pytest-suite-results/.
    Set RUN_WEB_E2E=true (or pass -IncludeWebE2E) to include web-backed integration tests.
    Called by both GitHub Actions and Azure DevOps pipelines.
#>
param(
    [ValidateSet('all', 'python', 'duckdb')]
    [string]$Suite = 'all',
    [switch]$IncludeWebE2E,
    [switch]$IncludeIntegration
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

$webE2EArg = if ($IncludeWebE2E) { @('--run-web-e2e') } else { @() }
$integrationArg = if ($IncludeIntegration) { @('--run-integration') } else { @() }

Write-Host "=== Running suite: $Suite ==="

python tools/local_dev/run_test_suite.py --suite $Suite @webE2EArg @integrationArg
$rc = $LASTEXITCODE

if ($rc -ne 0) {
    Write-Error "Tests failed."
    exit 1
}
Write-Host "=== Tests passed ==="
