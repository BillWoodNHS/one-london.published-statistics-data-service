param(
    [switch]$RecreateVenv
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$venvPath = Join-Path $repoRoot '.venv'

if ($RecreateVenv -and (Test-Path $venvPath)) {
    Remove-Item -Recurse -Force $venvPath
}

if (-not (Test-Path $venvPath)) {
    python -m venv $venvPath
}

$pythonExe = Join-Path $venvPath 'Scripts\python.exe'
$dbtExe = Join-Path $venvPath 'Scripts\dbt.exe'

& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -r .\function_app\requirements.txt -r .\requirements-dev.txt

if (Test-Path $dbtExe) {
    & $dbtExe deps --project-dir .\dbt
}

Write-Host 'Developer environment initialised.'
Write-Host "Python: $pythonExe"
Write-Host "dbt:    $dbtExe"
