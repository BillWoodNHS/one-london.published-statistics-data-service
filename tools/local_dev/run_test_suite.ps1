param(
    [ValidateSet('all', 'python', 'duckdb')]
    [string]$Suite = 'all',
    [switch]$ResumeLastFailed,
    [switch]$EnsureDeps,
    [switch]$RunWebE2E,
    [switch]$RunIntegration,
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'test_suite_config.json'),
    [string[]]$ExtraPytestArgs = @()
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
    $pythonExe = $venvPython
} else {
    $pythonExe = 'py'
}

$argsList = @('tools/local_dev/run_test_suite.py', '--suite', $Suite, '--config', $ConfigPath)
if ($ResumeLastFailed) { $argsList += '--resume-last-failed' }
if ($EnsureDeps) { $argsList += '--ensure-deps' }
if ($RunWebE2E) { $argsList += '--run-web-e2e' }
if ($RunIntegration) { $argsList += '--run-integration' }
if ($ExtraPytestArgs.Count -gt 0) {
    $argsList += '--extra-pytest-args'
    $argsList += $ExtraPytestArgs
}

if ($pythonExe -eq 'py') {
    & py -3 @argsList
} else {
    & $pythonExe @argsList
}

exit $LASTEXITCODE
