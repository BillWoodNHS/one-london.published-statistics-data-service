<#
.SYNOPSIS
    Run pre-commit checks using Ruff lint + format hooks.
    Called by both GitHub Actions and Azure DevOps pipelines.
#>
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
    $pythonExe = $venvPython
} else {
    $pythonExe = 'python'
}

$ruffExe = Join-Path $repoRoot '.venv\Scripts\ruff.exe'
if (-not (Test-Path $ruffExe)) {
    $ruffExe = $pythonExe
    $ruffArgs = @('-m', 'ruff')
} else {
    $ruffArgs = @()
}

Write-Host "=== Running pre-commit lint checks ==="
& $ruffExe @ruffArgs check .
$checkExit = $LASTEXITCODE
& $ruffExe @ruffArgs format --check .
$formatExit = $LASTEXITCODE

if ($checkExit -ne 0 -or $formatExit -ne 0) {
    Write-Error "Lint checks failed."
    exit 1
}
Write-Host "=== Lint checks passed ==="
