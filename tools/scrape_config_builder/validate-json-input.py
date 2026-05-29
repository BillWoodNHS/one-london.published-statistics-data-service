"""Validate a scrape-config-helper JSON input file.

Usage:
    python validate-json-input.py <path-to-json>

Exits 0 if valid, 1 if invalid.  All output goes to stdout so callers can
capture it directly.
"""

import json
import re
import sys
from pathlib import Path

ALLOWED_SCHEMA_VERSIONS = {"0.1", "2.0"}
ALLOWED_PAGE_ROLES = {
    "default",
    "archive",
    "subject_period_index",
    "sub_dataset_dedicated",
}
ALLOWED_PARTITIONING = {"none", "subject_period", "mixed"}
ALLOWED_ARCHIVE_PATTERNS = {"", "none", "sibling_pages_by_subject_period"}
ALLOWED_SUBJECT_PERIOD_PATTERNS = {
    "",
    "month_year",
    "compact_month_year",
    "fiscal_year_and_month",
    "quarter_year",
}
OBJECT_NAME_SUFFIX_PATTERN = re.compile(r"^[A-Z0-9_]+$")
RESERVED_OBJECT_NAME_PREFIXES = ("STG_", "PIPE_", "INGEST_", "RAW_")
ADLS_PATH_PREFIX_PATTERN = re.compile(
    r"^[a-z0-9_\-][a-z0-9_\-/]*[a-z0-9_\-]$|^[a-z0-9_\-]$"
)


def _validate_object_name_suffix(value: object) -> str | None:
    suffix = str(value or "").strip()
    if not suffix:
        return "must not be empty when provided"
    if suffix != suffix.upper():
        return "must use uppercase letters, digits, and underscores only"
    if not OBJECT_NAME_SUFFIX_PATTERN.fullmatch(suffix):
        return "must use uppercase letters, digits, and underscores only"
    if suffix.startswith(RESERVED_OBJECT_NAME_PREFIXES):
        return "must not include STG_, PIPE_, INGEST_, or RAW_ prefixes"
    return None


def _validate_adls_path_prefix(value: object) -> str | None:
    prefix = str(value or "").strip().strip("/")
    if not prefix:
        return "must not be empty when provided"
    if ".." in prefix.split("/"):
        return "must not contain path traversal (..)"
    if not ADLS_PATH_PREFIX_PATTERN.fullmatch(prefix):
        return (
            "must use only lowercase letters, digits, hyphens, underscores, and "
            "forward slashes — no leading/trailing slashes"
        )
    return None


def validate(path: Path) -> list[str]:
    """Return a list of error strings.  Empty list means valid."""
    errors: list[str] = []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"invalid JSON: {exc}"]

    if isinstance(payload, dict) and isinstance(payload.get("datasets"), list):
        records = payload["datasets"]
    elif isinstance(payload, dict):
        records = [payload]
    else:
        return ["root JSON must be an object (or an object with a 'datasets' array)"]

    for i, record in enumerate(records, start=1):
        prefix = f"record[{i}]"
        if not isinstance(record, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        schema_version = str(record.get("schema_version", "")).strip()
        if schema_version not in ALLOWED_SCHEMA_VERSIONS:
            errors.append(
                f"{prefix}.schema_version: '{schema_version or 'missing'}' not in "
                f"{sorted(ALLOWED_SCHEMA_VERSIONS)}"
            )

        if not str(record.get("dataset_id", "")).strip():
            errors.append(f"{prefix}.dataset_id: required")
        if not str(record.get("entry_url", "")).strip():
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

            if not str(target.get("sub_dataset_id", "")).strip():
                errors.append(f"{tprefix}.sub_dataset_id: required")

            if "object_name_suffix" in target:
                suffix_error = _validate_object_name_suffix(
                    target.get("object_name_suffix")
                )
                if suffix_error:
                    errors.append(f"{tprefix}.object_name_suffix: {suffix_error}")

            if "adls_path_prefix" in target:
                prefix_error = _validate_adls_path_prefix(
                    target.get("adls_path_prefix")
                )
                if prefix_error:
                    errors.append(f"{tprefix}.adls_path_prefix: {prefix_error}")

            sample_pages = target.get("sample_pages")
            if not isinstance(sample_pages, list) or not sample_pages:
                errors.append(f"{tprefix}.sample_pages: must be a non-empty list")
                continue

            hints = (
                target.get("hints", {}) if isinstance(target.get("hints"), dict) else {}
            )
            archive_pattern = str(hints.get("archive_pattern", "")).strip().lower()
            if archive_pattern not in ALLOWED_ARCHIVE_PATTERNS:
                errors.append(
                    f"{tprefix}.hints.archive_pattern: '{archive_pattern}' not in "
                    f"{sorted(ALLOWED_ARCHIVE_PATTERNS)}"
                )

            subject_period_pattern = (
                str(hints.get("subject_period_pattern", "")).strip().lower()
            )
            if subject_period_pattern not in ALLOWED_SUBJECT_PERIOD_PATTERNS:
                errors.append(
                    f"{tprefix}.hints.subject_period_pattern: "
                    f"'{subject_period_pattern}' not in "
                    f"{sorted(ALLOWED_SUBJECT_PERIOD_PATTERNS)}"
                )

            for p_idx, page in enumerate(sample_pages, start=1):
                pprefix = f"{tprefix}.sample_pages[{p_idx}]"
                if not isinstance(page, dict):
                    errors.append(f"{pprefix}: must be an object")
                    continue

                if not str(page.get("page_url", "")).strip():
                    errors.append(f"{pprefix}.page_url: required")

                page_role = str(page.get("page_role", "default")).strip().lower()
                if page_role not in ALLOWED_PAGE_ROLES:
                    errors.append(
                        f"{pprefix}.page_role: '{page_role}' not in "
                        f"{sorted(ALLOWED_PAGE_ROLES)}"
                    )

                partitioning = (
                    str(page.get("partitioning_strategy", "none")).strip().lower()
                )
                if partitioning not in ALLOWED_PARTITIONING:
                    errors.append(
                        f"{pprefix}.partitioning_strategy: '{partitioning}' not in "
                        f"{sorted(ALLOWED_PARTITIONING)}"
                    )

                samples = page.get("samples")
                if not isinstance(samples, list) or not samples:
                    errors.append(f"{pprefix}.samples: must be a non-empty list")
                    continue

                for s_idx, sample in enumerate(samples, start=1):
                    sprefix = f"{pprefix}.samples[{s_idx}]"
                    if not isinstance(sample, dict):
                        errors.append(f"{sprefix}: must be an object")
                        continue
                    if not str(sample.get("file_url", "")).strip():
                        errors.append(f"{sprefix}.file_url: required")

    return errors


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: validate-json-input.py <path-to-json>", file=sys.stderr)
        sys.exit(2)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)

    errors = validate(path)
    if errors:
        print("STEP1_JSON_VALID=false")
        for error in errors:
            print(f"ERROR: {error}")
        sys.exit(1)

    print("STEP1_JSON_VALID=true")


if __name__ == "__main__":
    main()
