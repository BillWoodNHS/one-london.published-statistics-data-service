param(
    [switch]$RecreateVenv
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

$venvPath = Join-Path $repoRoot '.venv'

if ($RecreateVenv -and (Test-Path $venvPath)) {
    Remove-Item -Recurse -Force $venvPath
}

if (-not (Test-Path $venvPath)) {
    # Prefer 3.12 for full dbt-duckdb compatibility; 3.14 is not yet supported by mashumaro.
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $resolved = $null
        foreach ($candidate in @('3.12', '3.11', '3.13')) {
            if (py "-$candidate" --version 2>$null) {
                $resolved = $candidate
                break
            }
        }
        if ($null -eq $resolved) {
            Write-Warning 'Could not find Python 3.11-3.13 via py launcher; falling back to default. dbt tests may skip on 3.14+.'
            py -3 -m venv $venvPath
        } else {
            Write-Host "Using Python $resolved for virtual environment."
            py "-$resolved" -m venv $venvPath
        }
    } else {
        python -m venv $venvPath
    }
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
