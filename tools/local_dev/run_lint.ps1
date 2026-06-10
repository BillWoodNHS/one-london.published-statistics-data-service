<#
.SYNOPSIS
    Run the shared lint suite locally.

.DESCRIPTION
    Wrapper around tools/linting/run_lint_suite.ps1 so local and CI use
    identical lint logic.
#>
param(
    [switch]$Fix,
    [switch]$EnsureDeps,
    [string[]]$Targets
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

$lintSuiteScript = Join-Path $repoRoot 'tools\linting\run_lint_suite.ps1'
$argsList = @()

if ($Fix) { $argsList += '-Fix' }
if ($EnsureDeps) { $argsList += '-EnsureDeps' }
if ($Targets -and $Targets.Count -gt 0) {
    $argsList += $Targets
}

& $lintSuiteScript @argsList
exit $LASTEXITCODE