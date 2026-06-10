<#
.SYNOPSIS
    Install local git pre-commit hooks for this repository.

.DESCRIPTION
    Installs pre-commit and registers the pre-commit hook so the shared
    lint suite runs before each commit.
#>
param(
    [switch]$EnsureDeps,
    [switch]$RunAllFiles
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
    Write-Host "Installing dev dependencies..."
    & $pythonExe -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Installing pre-commit hook..."
& $pythonExe -m pre_commit install
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($RunAllFiles) {
    Write-Host "Running pre-commit on all files..."
    & $pythonExe -m pre_commit run --all-files
    exit $LASTEXITCODE
}

Write-Host "Pre-commit hook installed."
