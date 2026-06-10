from __future__ import annotations

import csv
import hashlib
import io
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd
import requests

from .models import DiscoveredFile, LoadArtifact
from .period_coverage import infer_period_coverage


def _count_csv_rows(payload: bytes) -> int | None:
    """Count data rows in a CSV payload (excluding the header row)."""
    encodings = ("utf-8", "utf-8-sig", "latin-1")
    for encoding in encodings:
        try:
            text = payload.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        return None

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return 0
    return max(0, len(rows) - 1)


def _to_iso_partition_value(raw_value: str) -> str:
    """Convert a raw value to an ISO-like partition value for use in paths."""
    value = raw_value.strip().replace(" ", "-").replace("/", "-").replace(":", "")
    return value


def _adls_path(
    adls_path_prefix: str,
    downloaded_at: str,
    filename: str,
) -> str:
    """Build an ADLS path for a file.

    Uses the explicit adls_path_prefix from the manifest target, download
    timestamp partitions, and filename.
    """
    safe_ts = _to_iso_partition_value(downloaded_at)
    safe_year = safe_ts[:4] if len(safe_ts) >= 4 else "unknown"
    safe_month = safe_ts[4:6] if len(safe_ts) >= 6 else "unknown"
    return (
        f"{adls_path_prefix}/download_year={safe_year}/"
        f"download_month={safe_month}/"
        f"downloaded_at={safe_ts}/{filename}"
    )


def _download(url: str) -> bytes:
    """Download content from a URL and return as bytes."""
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.content


def _sha256(data: bytes) -> str:
    """Compute the SHA-256 hash of the given bytes."""
    return hashlib.sha256(data).hexdigest()


def _first_csv_from_zip(payload: bytes) -> Tuple[str, bytes, Dict[str, Any]]:
    """Extract the first CSV or Excel file from a ZIP payload.

    Converts Excel to CSV if no CSV is found.
    """
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        for name in zf.namelist():
            if name.lower().endswith(".csv"):
                csv_payload = zf.read(name)
                metrics: Dict[str, Any] = {
                    "source_file_type": "zip",
                    "extracted_from_archive": True,
                    "converted_to_csv": False,
                    "archive_member_name": Path(name).name,
                    "raw_row_count": _count_csv_rows(csv_payload),
                    "normalized_row_count": _count_csv_rows(csv_payload),
                }
                return Path(name).name, csv_payload, metrics

        for name in zf.namelist():
            if name.lower().endswith((".xlsx", ".xls")):
                data = zf.read(name)
                ext = Path(name).suffix.lower() or ".xlsx"
                csv_name, csv_payload, metrics = _excel_to_csv(
                    Path(name).stem, data, ext
                )
                metrics["source_file_type"] = "zip"
                metrics["extracted_from_archive"] = True
                metrics["archive_member_name"] = Path(name).name
                return csv_name, csv_payload, metrics

    raise ValueError("ZIP did not contain CSV or Excel files")


def _excel_to_csv(
    base_name: str, payload: bytes, extension: str = ".xlsx"
) -> Tuple[str, bytes, Dict[str, Any]]:
    """Convert an Excel file payload to CSV bytes.

    Returns the new filename and content.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp:
        tmp.write(payload)
        tmp_path = tmp.name

    try:
        df = pd.read_excel(tmp_path)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(df.columns.tolist())
        writer.writerows(df.values.tolist())
        csv_payload = buffer.getvalue().encode("utf-8")
        row_count = int(len(df.index))
        metrics: Dict[str, Any] = {
            "source_file_type": "excel",
            "extracted_from_archive": False,
            "converted_to_csv": True,
            "archive_member_name": None,
            "raw_row_count": row_count,
            "normalized_row_count": row_count,
        }
        return f"{base_name}.csv", csv_payload, metrics
    finally:
        os.unlink(tmp_path)


def normalize_to_csv(file_url: str) -> Tuple[str, bytes, str, Dict[str, Any]]:
    """Download and normalize a file from a URL to CSV.

    Returns filename, content bytes, SHA-256 hash, and telemetry metrics.
    """
    payload = _download(file_url)
    filename, csv_payload, content_hash, metrics = normalize_payload_to_csv(
        Path(file_url).name, payload
    )
    metrics["source_bytes"] = len(payload)
    metrics["normalized_bytes"] = len(csv_payload)
    return filename, csv_payload, content_hash, metrics


def normalize_payload_to_csv(
    source_name: str, payload: bytes
) -> Tuple[str, bytes, str, Dict[str, Any]]:
    """Normalize a file payload (CSV, ZIP, or Excel) to CSV.

    Returns filename, content bytes, SHA-256 hash, and telemetry metrics.
    """
    content_hash = _sha256(payload)
    lowered = source_name.lower()

    if lowered.endswith(".csv"):
        metrics: Dict[str, Any] = {
            "source_file_type": "csv",
            "extracted_from_archive": False,
            "converted_to_csv": False,
            "archive_member_name": None,
            "raw_row_count": _count_csv_rows(payload),
            "normalized_row_count": _count_csv_rows(payload),
            "source_bytes": len(payload),
            "normalized_bytes": len(payload),
        }
        return Path(source_name).name, payload, content_hash, metrics

    if lowered.endswith(".zip"):
        name, csv_payload, metrics = _first_csv_from_zip(payload)
        metrics["source_bytes"] = len(payload)
        metrics["normalized_bytes"] = len(csv_payload)
        return name, csv_payload, content_hash, metrics

    if lowered.endswith(".xlsx") or lowered.endswith(".xls"):
        ext = Path(source_name).suffix.lower() or ".xlsx"
        name, csv_payload, metrics = _excel_to_csv(Path(source_name).stem, payload, ext)
        metrics["source_bytes"] = len(payload)
        metrics["normalized_bytes"] = len(csv_payload)
        return name, csv_payload, content_hash, metrics

    raise ValueError(f"Unsupported file type for source: {source_name}")


def build_artifact(
    file: DiscoveredFile,
    filename: str,
    content_hash: str,
    downloaded_at: str,
    acquisition_method: str = "automated",
    fallback_reason: str = "",
) -> LoadArtifact:
    """Build a LoadArtifact object for a discovered file.

    Includes ADLS path and metadata.
    """
    coverage = infer_period_coverage(
        subject_period_hint=file.subject_period_hint,
        link_text=file.link_text,
        source_url=file.source_url,
        page_text=file.page_text,
        duration_type_hint=(
            file.period_coverage_hint.file_scope.duration_type
            if file.period_coverage_hint
            else "unknown"
        ),
        duration_value_hint=(
            file.period_coverage_hint.file_scope.duration_value
            if file.period_coverage_hint
            else None
        ),
        duration_unit_hint=(
            file.period_coverage_hint.file_scope.duration_unit
            if file.period_coverage_hint
            else None
        ),
        fiscal_year_start_month_hint=(
            file.period_coverage_hint.file_scope.fiscal_year_start_month
            if file.period_coverage_hint
            else None
        ),
    )
    adls_path_prefix = (
        file.adls_path_prefix or f"{file.series_id}/{file.sub_dataset_id}"
    )
    return LoadArtifact(
        adls_path=_adls_path(
            adls_path_prefix,
            downloaded_at,
            filename,
        ),
        source_url=file.source_url,
        series_id=file.series_id,
        sub_dataset_id=file.sub_dataset_id,
        subject_period_from=coverage.subject_period_from,
        subject_period_to=coverage.subject_period_to,
        subject_period_coverage_type=coverage.coverage_type,
        subject_period_inference_method=coverage.inference_method,
        subject_period_inference_source=coverage.inference_source,
        subject_period_inference_confidence=coverage.confidence,
        file_scope_duration_type=(
            file.period_coverage_hint.file_scope.duration_type
            if file.period_coverage_hint
            else "unknown"
        ),
        file_scope_duration_value=(
            file.period_coverage_hint.file_scope.duration_value
            if file.period_coverage_hint
            else None
        ),
        file_scope_duration_unit=(
            file.period_coverage_hint.file_scope.duration_unit
            if file.period_coverage_hint and file.period_coverage_hint.file_scope.duration_unit
            else ""
        ),
        file_scope_fiscal_year_start_month=(
            file.period_coverage_hint.file_scope.fiscal_year_start_month
            if file.period_coverage_hint
            else None
        ),
        breakdown_granularity=(
            file.period_coverage_hint.breakdown_granularity
            if file.period_coverage_hint
            else []
        ),
        publication_date=file.publication_date_value or "",
        source_content_hash=content_hash,
        acquisition_method=acquisition_method,
        fallback_reason=fallback_reason,
        downloaded_at=downloaded_at,
        adls_path_prefix=adls_path_prefix,
    )


def normalize_local_file_to_csv(
    local_file: Path,
) -> Tuple[str, bytes, str, Dict[str, Any]]:
    """Normalize a local file to CSV, returning filename, content, hash, and metrics."""
    payload = local_file.read_bytes()
    return normalize_payload_to_csv(local_file.name, payload)
