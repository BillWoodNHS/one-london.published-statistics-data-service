$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$env:LOCAL_STORAGE_MODE = 'true'
$env:LOCAL_STORAGE_ROOT = (Join-Path $repoRoot '.local_adls')
$env:MANIFEST_ROOT = (Join-Path $repoRoot 'tests\fixtures\manifests')
$env:MANUAL_INPUT_PREFIX = 'manual'
$env:RUN_WEB_E2E = 'true'
$env:DUCKDB_FILE = (Join-Path $repoRoot '.local_adls\local_validation.duckdb')

python .\tools\run_local_e2e.py
