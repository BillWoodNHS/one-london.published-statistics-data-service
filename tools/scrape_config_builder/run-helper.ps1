param(
    [Parameter(Mandatory = $true)]
    [string]$InputJson,

    [string]$OutputDir = "tools/scrape_config_builder/helper_generated",

    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -Path $InputJson)) {
    Write-Error "Input JSON not found: $InputJson"
    exit 1
}

Write-Host "===STEP1_JSON_SCHEMA_AND_ENUM_VALIDATION==="
$ValidatorScript = Join-Path $PSScriptRoot "validate-json-input.py"
python $ValidatorScript $InputJson
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$datasetId = python -c "import json,sys; p=json.load(open(sys.argv[1], encoding='utf-8')); records=p.get('datasets') if isinstance(p,dict) and isinstance(p.get('datasets'),list) else [p] if isinstance(p,dict) else []; print((records[0].get('dataset_id') or '').strip())" $InputJson
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($datasetId)) {
    Write-Error "Could not determine dataset_id from input JSON: $InputJson"
    exit 1
}

if ($ValidateOnly) {
    Write-Host "===VALIDATING ONLY==="
    Write-Host "===STEP2_GENERATE_YAML==="
    Write-Host "SKIPPED"
    exit 0
}

Write-Host "===STEP2_GENERATE_YAML==="
python tools/scrape_config_builder/scrape-config-helper.py --input-json $InputJson --output-dir $OutputDir
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
Write-Host "===STEP3_LIVE_DETECTION_COUNTS==="
$matchesPath = Join-Path $OutputDir "$datasetId/latest/reports/matches_found.csv"
if (-not (Test-Path -Path $matchesPath)) {
    Write-Error "matches_found.csv not found at: $matchesPath"
    exit 1
}

$rows = Import-Csv $matchesPath
if (-not $rows) {
    Write-Host "No rows found in matches_found.csv"
    exit 0
}

$summary = $rows |
    Group-Object sub_dataset_id, status |
    Sort-Object Name |
    Select-Object @{Name = 'sub_dataset_id'; Expression = { $_.Group[0].sub_dataset_id }},
        @{Name = 'status'; Expression = { $_.Group[0].status }},
        @{Name = 'count'; Expression = { $_.Count }}

$summary | Format-Table -AutoSize
Write-Host "Matches CSV: $matchesPath"
Write-Host "Generated YAML dir: $(Join-Path $OutputDir "$datasetId/latest/generated_configs")"
