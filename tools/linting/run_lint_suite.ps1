<#
.SYNOPSIS
    Run the shared Ruff lint suite.

.DESCRIPTION
    Canonical lint entrypoint used by CI wrappers, local wrappers, and pre-commit.
    Default mode runs:
      - ruff check
      - ruff format --check

    Use -Fix to run:
      - ruff check --fix
      - ruff format
#>
param(
    [switch]$Fix,
    [switch]$EnsureDeps,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Targets
)

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

if ($EnsureDeps) {
    Write-Host "Installing lint dependencies from requirements-dev.txt..."
    & $pythonExe -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$ruffExe = Join-Path $repoRoot '.venv\Scripts\ruff.exe'
if (-not (Test-Path $ruffExe)) {
    $ruffExe = $pythonExe
    $ruffArgs = @('-m', 'ruff')
} else {
    $ruffArgs = @()
}

if (-not $Targets -or $Targets.Count -eq 0) {
    $Targets = @('.')
}

if ($Fix) {
    Write-Host "=== Running ruff check --fix ==="
    & $ruffExe @ruffArgs check --fix @Targets
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "=== Running ruff format ==="
    & $ruffExe @ruffArgs format @Targets
    exit $LASTEXITCODE
}

Write-Host "=== Running ruff check ==="
& $ruffExe @ruffArgs check @Targets
$checkExit = $LASTEXITCODE

Write-Host "=== Running ruff format --check ==="
& $ruffExe @ruffArgs format --check @Targets
$formatExit = $LASTEXITCODE

if ($checkExit -ne 0 -or $formatExit -ne 0) {
    Write-Error "Lint checks failed."
    exit 1
}

Write-Host "=== Lint checks passed ==="