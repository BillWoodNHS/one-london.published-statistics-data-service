param(
    [Parameter(Mandatory = $true)]
    [string]$InputJson,

    [string]$OutputDir = "",

    [switch]$ValidateOnly,

    [switch]$SkipScanScrape
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -Path $InputJson)) {
    Write-Error "Input JSON not found: $InputJson"
    exit 1
}

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($InputJson)
    $OutputDir = "logs/review_$stem"
}

Write-Host "===STEP1_JSON_SCHEMA_AND_ENUM_VALIDATION==="
$validator = @"
import json
import sys
from pathlib import Path

allowed_schema_versions = {"0.1", "2.0"}
allowed_page_roles = {"default", "archive", "subject_period_index", "sub_dataset_dedicated"}
allowed_partitioning = {"none", "subject_period", "mixed"}
allowed_archive_patterns = {"", "none", "sibling_pages_by_subject_period"}
allowed_subject_period_patterns = {
    "",
    "month_year",
    "compact_month_year",
    "fiscal_year_and_month",
    "quarter_year",
}

path = Path(sys.argv[1])
errors = []

try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    print("STEP1_JSON_VALID=false")
    print(f"ERROR: invalid JSON parse: {exc}")
    sys.exit(1)

records = payload.get("datasets") if isinstance(payload, dict) and isinstance(payload.get("datasets"), list) else [payload] if isinstance(payload, dict) else None
if records is None:
    print("STEP1_JSON_VALID=false")
    print("ERROR: root JSON must be an object (or an object with a 'datasets' array)")
    sys.exit(1)

for i, record in enumerate(records, start=1):
    prefix = f"record[{i}]"
    if not isinstance(record, dict):
        errors.append(f"{prefix}: must be an object")
        continue

    schema_version = str(record.get("schema_version", "")).strip()
    if schema_version not in allowed_schema_versions:
        errors.append(f"{prefix}.schema_version: '{schema_version or 'missing'}' not in {sorted(allowed_schema_versions)}")

    dataset_id = str(record.get("dataset_id", "")).strip()
    entry_url = str(record.get("entry_url", "")).strip()
    if not dataset_id:
        errors.append(f"{prefix}.dataset_id: required")
    if not entry_url:
        errors.append(f"{prefix}.entry_url: required")

    targets = record.get("targets")
    if not isinstance(targets, list) or not targets:
        errors.append(f"{prefix}.targets: must be a non-empty list")
        continue

    for t_idx, target in enumerate(targets, start=1):
        tprefix = f"{prefix}.targets[{t_idx}]"
        if not isinstance(target, dict):
            errors.append(f"{tprefix}: must be an object")
            continue

        sub_dataset_id = str(target.get("sub_dataset_id", "")).strip()
        if not sub_dataset_id:
            errors.append(f"{tprefix}.sub_dataset_id: required")

        sample_pages = target.get("sample_pages")
        if not isinstance(sample_pages, list) or not sample_pages:
            errors.append(f"{tprefix}.sample_pages: must be a non-empty list")
            continue

        hints = target.get("hints", {}) if isinstance(target.get("hints"), dict) else {}
        archive_pattern = str(hints.get("archive_pattern", "")).strip().lower()
        if archive_pattern not in allowed_archive_patterns:
            errors.append(
                f"{tprefix}.hints.archive_pattern: '{archive_pattern}' not in {sorted(allowed_archive_patterns)}"
            )

        subject_period_pattern = str(hints.get("subject_period_pattern", "")).strip().lower()
        if subject_period_pattern not in allowed_subject_period_patterns:
            errors.append(
                f"{tprefix}.hints.subject_period_pattern: '{subject_period_pattern}' not in {sorted(allowed_subject_period_patterns)}"
            )

        for p_idx, page in enumerate(sample_pages, start=1):
            pprefix = f"{tprefix}.sample_pages[{p_idx}]"
            if not isinstance(page, dict):
                errors.append(f"{pprefix}: must be an object")
                continue

            page_url = str(page.get("page_url", "")).strip()
            if not page_url:
                errors.append(f"{pprefix}.page_url: required")

            page_role = str(page.get("page_role", "default")).strip().lower()
            if page_role not in allowed_page_roles:
                errors.append(f"{pprefix}.page_role: '{page_role}' not in {sorted(allowed_page_roles)}")

            partitioning = str(page.get("partitioning_strategy", "none")).strip().lower()
            if partitioning not in allowed_partitioning:
                errors.append(f"{pprefix}.partitioning_strategy: '{partitioning}' not in {sorted(allowed_partitioning)}")

            samples = page.get("samples")
            if not isinstance(samples, list) or not samples:
                errors.append(f"{pprefix}.samples: must be a non-empty list")
                continue

            for s_idx, sample in enumerate(samples, start=1):
                sprefix = f"{pprefix}.samples[{s_idx}]"
                if not isinstance(sample, dict):
                    errors.append(f"{sprefix}: must be an object")
                    continue
                file_url = str(sample.get("file_url", "")).strip()
                if not file_url:
                    errors.append(f"{sprefix}.file_url: required")

if errors:
    print("STEP1_JSON_VALID=false")
    for e in errors:
        print(f"ERROR: {e}")
    sys.exit(1)

print("STEP1_JSON_VALID=true")
"@

python -c $validator $InputJson
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($ValidateOnly) {
    Write-Host "===VALIDATING ONLY==="
    Write-Host "===STEP2_GENERATE_YAML==="
    Write-Host "SKIPPED"
    Write-Host "===STEP3_LIVE_DETECTION_COUNTS==="
    Write-Host "SKIPPED"
    exit 0
}

Write-Host "===STEP2_GENERATE_YAML==="
python tools/scrape_config_builder/scrape-config-helper.py --input-json $InputJson --output-dir $OutputDir
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($SkipScanScrape) {
    Write-Host "===STEP3_LIVE_DETECTION_COUNTS==="
    Write-Host "SKIPPED"
    exit 0
}

Write-Host "===STEP3_LIVE_DETECTION_COUNTS==="
$matchesPath = Join-Path $OutputDir "matches_found.csv"
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
