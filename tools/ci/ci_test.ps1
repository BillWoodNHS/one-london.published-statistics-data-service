<#
.SYNOPSIS
    Run the pytest unit test suite (no web E2E by default).
    Set RUN_WEB_E2E=true to include web-backed integration tests.
    Called by both GitHub Actions and Azure DevOps pipelines.
#>
param(
    [switch]$IncludeWebE2E
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($IncludeWebE2E) {
    $env:RUN_WEB_E2E = "true"
    Write-Host "=== Running full test suite (including web E2E) ==="
} else {
    Write-Host "=== Running unit test suite ==="
}

python -m pytest -q
$rc = $LASTEXITCODE

Remove-Item Env:RUN_WEB_E2E -ErrorAction SilentlyContinue

if ($rc -ne 0) {
    Write-Error "Tests failed."
    exit 1
}
Write-Host "=== Tests passed ==="
