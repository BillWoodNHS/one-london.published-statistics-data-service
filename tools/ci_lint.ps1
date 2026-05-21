<#
.SYNOPSIS
    Run pre-commit checks using Ruff lint + format hooks.
    Called by both GitHub Actions and Azure DevOps pipelines.
#>
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "=== Running pre-commit lint checks ==="
python -m pre_commit run --all-files
if ($LASTEXITCODE -ne 0) {
    Write-Error "Lint checks failed."
    exit 1
}
Write-Host "=== Lint checks passed ==="
