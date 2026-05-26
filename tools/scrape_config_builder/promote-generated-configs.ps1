param(
    [string[]]$Dataset,

    [string]$RunId = "latest",

    [string]$OutputRoot = "tools/scrape_config_builder/helper_generated",

    [string]$ConfigDir = "config/datasets",

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "promote-generated-configs.py"

if (-not (Test-Path -Path $pythonScript)) {
    Write-Error "Python promotion script not found: $pythonScript"
    exit 1
}

$pythonArgs = @(
    $pythonScript,
    "--run-id", $RunId,
    "--output-root", $OutputRoot,
    "--config-dir", $ConfigDir
)

if ($Dataset) {
    foreach ($datasetId in $Dataset) {
        if (-not [string]::IsNullOrWhiteSpace($datasetId)) {
            $pythonArgs += @("--dataset", $datasetId)
        }
    }
}

if ($DryRun) {
    $pythonArgs += "--dry-run"
}

python @pythonArgs
exit $LASTEXITCODE
