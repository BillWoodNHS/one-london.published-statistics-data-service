param(
	[switch]$UseFixtures,
	[ValidateSet('full', 'scrape-only', 'load-only')]
	[string]$ExecutionMode = 'full',
	[string]$DatasetProfileFile = '',
	[int]$MaxFilesPerDataset = 0,
	[int]$MaxFilesPerTarget = 0,
	[int]$MaxTotalFiles = 0
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

$env:LOCAL_STORAGE_MODE = 'true'
$env:LOCAL_STORAGE_ROOT = (Join-Path $repoRoot '.local_adls')
$manifestRoot = if ($UseFixtures) {
	Join-Path $repoRoot 'tests\fixtures\manifests'
} else {
	Join-Path $repoRoot 'config\datasets'
}
$env:MANIFEST_ROOT = $manifestRoot
$env:MANUAL_INPUT_PREFIX = 'manual'
$env:RUN_WEB_E2E = 'true'
$env:DUCKDB_FILE = (Join-Path $repoRoot '.local_adls\local_validation.duckdb')

$argsList = @(
	'.\tools\local_dev\run_local_e2e.py',
	'--execution-mode', $ExecutionMode,
	'--max-files-per-dataset', [string][Math]::Max(0, $MaxFilesPerDataset),
	'--max-files-per-target', [string][Math]::Max(0, $MaxFilesPerTarget),
	'--max-total-files', [string][Math]::Max(0, $MaxTotalFiles)
)

if ($UseFixtures) {
	$argsList += '--use-fixtures'
}
if ($DatasetProfileFile) {
	$argsList += '--dataset-profile-file'
	$argsList += $DatasetProfileFile
}

python @argsList
