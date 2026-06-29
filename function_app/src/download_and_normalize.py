from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from openpyxl.utils import column_index_from_string

from .models import (
    DiscoveredFile,
    LoadArtifact,
    NormalizedFile,
    SubTableConfig,
    TargetConfig,
    UnpivotConfig,
)
from .period_coverage import infer_period_coverage


def _decode_csv_text(payload: bytes) -> Optional[str]:
    """Decode CSV bytes, trying common encodings in turn."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _count_csv_rows(payload: bytes) -> int | None:
    """Count data rows in a CSV payload (excluding the header row)."""
    text = _decode_csv_text(payload)
    if text is None:
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


def resolve_sub_table_adls_prefix(
    filename: str, metrics: Dict[str, Any], target: TargetConfig
) -> str:
    """Return the ADLS path prefix for a normalized file.

    If the file was produced by sheet-based splitting, its metrics already
    carry the resolved sub-table prefix (decided during normalization, since
    sheet names can't be recovered from the output filename) — return that
    directly. Otherwise, test the file's basename against each sub-table's
    filename_patterns (the zip-extraction case). The first sub-table with any
    matching pattern wins. If neither applies, the file is routed to the
    parent target's adls_path_prefix.
    """
    sheet_prefix = metrics.get("matched_sub_table_adls_path_prefix")
    if sheet_prefix:
        return sheet_prefix

    for st in target.sub_tables:
        if st.filename_patterns and any(
            re.search(p, filename, re.IGNORECASE) for p in st.filename_patterns
        ):
            return st.adls_path_prefix
    return target.adls_path_prefix


def _all_csvs_from_zip(
    payload: bytes, target: Optional[TargetConfig] = None
) -> List[Tuple[str, bytes, Dict[str, Any]]]:
    # Extract all CSV/extractable files from a ZIP payload and return them individually
    results: List[Tuple[str, bytes, Dict[str, Any]]] = []

    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        for name in zf.namelist():
            lowered = name.lower()

            if lowered.endswith(".csv"):
                # read csv and append to results
                csv_payload = zf.read(name)
                metrics: Dict[str, Any] = {
                    "source_file_type": "zip",
                    "extracted_from_archive": True,
                    "converted_to_csv": False,
                    "archive_member_name": Path(name).name,
                    "raw_row_count": _count_csv_rows(csv_payload),
                    "normalized_row_count": _count_csv_rows(csv_payload),
                }
                results.append((Path(name).name, csv_payload, metrics))
            elif lowered.endswith((".xlsx", ".xls")):
                # convert excel to csv and append to results
                data = zf.read(name)
                ext = Path(name).suffix.lower() or ".xlsx"
                for csv_name, csv_payload, metrics in _excel_to_csv(
                    Path(name).stem, data, ext, target
                ):
                    metrics["source_file_type"] = "zip"
                    metrics["extracted_from_archive"] = True
                    metrics["archive_member_name"] = Path(name).name
                    results.append((csv_name, csv_payload, metrics))
            elif lowered.endswith(".ods"):
                # convert ods to csv and append to results
                data = zf.read(name)
                ext = Path(name).suffix.lower() or ".ods"
                for csv_name, csv_payload, metrics in _ods_to_csv(
                    Path(name).stem, data, ext, target
                ):
                    metrics["source_file_type"] = "zip"
                    metrics["extracted_from_archive"] = True
                    metrics["archive_member_name"] = Path(name).name
                    results.append((csv_name, csv_payload, metrics))
            elif lowered.endswith("/"):
                # skip nested sub-directories
                continue

    if not results:
        raise ValueError("ZIP did not contain CSV, Excel, or ODS files")

    return results


def _parse_start_cell(start_cell: Optional[str]) -> Tuple[int, int]:
    """Convert a top-left cell reference like 'B5' into (skiprows, start_col_idx).

    skiprows is the number of rows above the header row to skip. start_col_idx
    is the 0-based index of the leftmost column to keep — columns to its left
    are dropped after reading, since the table's right-hand extent isn't
    specified and pandas can't pre-trim to an open-ended column range.
    """
    if not start_cell:
        return 0, 0
    match = re.fullmatch(r"([A-Za-z]+)([0-9]+)", start_cell)
    col_letters, row_number = match.group(1).upper(), int(match.group(2))
    return row_number - 1, column_index_from_string(col_letters) - 1


def _slugify_sheet_name(sheet_name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", sheet_name).strip("_")
    return slug or "sheet"


def _unpivot(df: pd.DataFrame, config: UnpivotConfig) -> pd.DataFrame:
    """Melt all non-id columns into long format per an UnpivotConfig.

    Generic reshape — the melted column headers (dates, metric names,
    anything else) are kept as-is in variable_column_name; no
    interpretation happens here.
    """
    missing = [c for c in config.id_columns if c not in df.columns]
    if missing:
        raise ValueError(f"unpivot.id_columns not found in source columns: {missing}")
    return df.melt(
        id_vars=config.id_columns,
        var_name=config.variable_column_name,
        value_name=config.value_column_name,
    )


def _read_sheet_to_csv_row(
    tmp_path: str,
    sheet_name: str,
    engine: str,
    start_cell: Optional[str],
    unpivot: Optional[UnpivotConfig] = None,
) -> Tuple[bytes, int]:
    skiprows, start_col_idx = _parse_start_cell(start_cell)
    df = pd.read_excel(
        tmp_path,
        sheet_name=sheet_name,
        engine=engine,
        **({"skiprows": skiprows} if skiprows else {}),
    )
    if start_col_idx:
        df = df.iloc[:, start_col_idx:]
    if unpivot:
        df = _unpivot(df, unpivot)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(df.columns.tolist())
    writer.writerows(df.values.tolist())
    return buffer.getvalue().encode("utf-8"), int(len(df.index))


def _spreadsheet_to_csvs(
    base_name: str,
    tmp_path: str,
    *,
    engine: str,
    source_file_type: str,
    sub_tables: List[SubTableConfig],
    excel_sheet: Optional[str],
    target_unpivot: Optional[UnpivotConfig] = None,
) -> List[Tuple[str, bytes, Dict[str, Any]]]:
    """Split a spreadsheet workbook into one or more CSV outputs.

    Shared by Excel and ODS handling — both formats support multiple sheets
    and the same pandas read_excel kwargs, just a different engine.
    """
    sheet_routed = [st for st in sub_tables if st.sheet_name_patterns]

    if not sheet_routed:
        csv_payload, row_count = _read_sheet_to_csv_row(
            tmp_path, excel_sheet or 0, engine, None, target_unpivot
        )
        metrics: Dict[str, Any] = {
            "source_file_type": source_file_type,
            "extracted_from_archive": False,
            "converted_to_csv": True,
            "archive_member_name": None,
            "raw_row_count": row_count,
            "normalized_row_count": row_count,
        }
        return [(f"{base_name}.csv", csv_payload, metrics)]

    with pd.ExcelFile(tmp_path, engine=engine) as workbook:
        available_sheets = list(workbook.sheet_names)
    matched_sheets: set[str] = set()
    results: List[Tuple[str, bytes, Dict[str, Any]]] = []

    for st in sheet_routed:
        for sheet_name in available_sheets:
            if sheet_name in matched_sheets:
                continue
            if not any(
                re.search(p, sheet_name, re.IGNORECASE) for p in st.sheet_name_patterns
            ):
                continue
            matched_sheets.add(sheet_name)
            csv_payload, row_count = _read_sheet_to_csv_row(
                tmp_path, sheet_name, engine, st.start_cell, st.unpivot
            )
            results.append(
                (
                    f"{base_name}__{_slugify_sheet_name(sheet_name)}.csv",
                    csv_payload,
                    {
                        "source_file_type": source_file_type,
                        "extracted_from_archive": False,
                        "converted_to_csv": True,
                        "archive_member_name": None,
                        "raw_row_count": row_count,
                        "normalized_row_count": row_count,
                        "source_sheet_name": sheet_name,
                        "matched_sub_table_object_name_suffix": st.object_name_suffix,
                        "matched_sub_table_adls_path_prefix": st.adls_path_prefix,
                    },
                )
            )

    # Sheets matching no sub_table pattern are deliberately discarded here
    # (presumed to be formatted reports/summaries, not data) — unlike an
    # unmatched zip member, which still falls through to the parent target's
    # adls_path_prefix in resolve_sub_table_adls_prefix.
    if not results:
        raise ValueError(
            f"None of the configured sheet_name_patterns rules matched any "
            f"sheet in {base_name}{Path(tmp_path).suffix} "
            f"(available sheets: {available_sheets})"
        )

    return results


def _excel_to_csv(
    base_name: str,
    payload: bytes,
    extension: str = ".xlsx",
    target: Optional[TargetConfig] = None,
) -> List[Tuple[str, bytes, Dict[str, Any]]]:
    """Convert an Excel file payload to one or more CSV outputs.

    Returns a list of (filename, csv_bytes, metrics) — more than one entry
    when the target defines sheet-splitting sub_tables that match multiple
    sheets in the workbook.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp:
        tmp.write(payload)
        tmp_path = tmp.name

    try:
        return _spreadsheet_to_csvs(
            base_name,
            tmp_path,
            engine="openpyxl" if extension == ".xlsx" else None,
            source_file_type="excel",
            sub_tables=target.sub_tables if target else [],
            excel_sheet=target.excel_sheet if target else None,
            target_unpivot=target.unpivot if target else None,
        )
    finally:
        os.unlink(tmp_path)


def _ods_to_csv(
    base_name: str,
    payload: bytes,
    extension: str = ".ods",
    target: Optional[TargetConfig] = None,
) -> List[Tuple[str, bytes, Dict[str, Any]]]:
    """Convert an ODS file payload to one or more CSV outputs.

    Returns a list of (filename, csv_bytes, metrics) — more than one entry
    when the target defines sheet-splitting sub_tables that match multiple
    sheets in the workbook.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp:
        tmp.write(payload)
        tmp_path = tmp.name

    try:
        return _spreadsheet_to_csvs(
            base_name,
            tmp_path,
            engine="odf",
            source_file_type="ods",
            sub_tables=target.sub_tables if target else [],
            excel_sheet=target.excel_sheet if target else None,
            target_unpivot=target.unpivot if target else None,
        )
    finally:
        os.unlink(tmp_path)


def normalize_to_csv(
    item: DiscoveredFile, target: Optional[TargetConfig] = None
) -> List[NormalizedFile]:
    """Download and normalize a file from a URL to CSV.

    Returns a list of NormalizedFile objects.
    """
    payload = _download(item.source_url)
    raw_results = normalize_payload_to_csv(Path(item.source_url).name, payload, target)

    normalized_files: List[NormalizedFile] = []
    for filename, csv_payload, content_hash, metrics in raw_results:
        metrics["source_bytes"] = len(payload)
        metrics["normalized_bytes"] = len(csv_payload)
        normalized_files.append(
            NormalizedFile(
                filename=filename,
                payload=csv_payload,
                content_hash=content_hash,
                metrics=metrics,
                dataset_id=item.dataset_id,
                sub_dataset_id=item.sub_dataset_id,
                series_id=item.series_id,
                source_url=item.source_url,
                publication_date_value=item.publication_date_value,
                link_text=item.link_text,
                subject_period_hint=item.subject_period_hint,
                page_text=item.page_text,
                period_coverage_hint=item.period_coverage_hint,
                adls_path_prefix=item.adls_path_prefix,
            )
        )

    return normalized_files


def _finalize_spreadsheet_outputs(
    sheet_outputs: List[Tuple[str, bytes, Dict[str, Any]]],
    source_payload: bytes,
    source_content_hash: str,
) -> List[Tuple[str, bytes, str, Dict[str, Any]]]:
    """Attach content hashes and source/normalized byte sizes to sheet outputs.

    When a workbook produces exactly one output (today's behaviour: no
    sheet-splitting sub_tables configured), the content hash is the hash of
    the original source payload, unchanged from before this feature existed.
    When splitting produces multiple outputs, each needs its own hash (the
    source payload hash would be identical and wrongly identical across
    distinct sheets) — mirroring how zip extraction already hashes each
    extracted file individually.
    """
    use_per_output_hash = len(sheet_outputs) > 1
    outputs = []
    for name, csv_payload, metrics in sheet_outputs:
        outputs.append(
            (
                name,
                csv_payload,
                _sha256(csv_payload) if use_per_output_hash else source_content_hash,
                {
                    **metrics,
                    "source_bytes": len(source_payload),
                    "normalized_bytes": len(csv_payload),
                },
            )
        )
    return outputs


def normalize_payload_to_csv(
    source_name: str, payload: bytes, target: Optional[TargetConfig] = None
) -> List[Tuple[str, bytes, str, Dict[str, Any]]]:
    ## Normalize a file payload (CSV, ZIP, Excel, or ODS) to CSV.
    ## Returns a list of filenames, content bytes, SHA-256 hash, and telemetry metrics.
    ## List is used to account for ZIP files that may contain multiple CSVs
    ## or extractable files, and for Excel/ODS workbooks split into multiple
    ## sheet-based outputs.

    content_hash = _sha256(payload)
    lowered = source_name.lower()

    if lowered.endswith(".csv"):
        if target and target.unpivot:
            text = _decode_csv_text(payload)
            if text is None:
                raise ValueError(f"Could not decode CSV for unpivot: {source_name}")
            df = pd.read_csv(io.StringIO(text))
            raw_row_count = int(len(df.index))
            df = _unpivot(df, target.unpivot)
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(df.columns.tolist())
            writer.writerows(df.values.tolist())
            csv_payload = buffer.getvalue().encode("utf-8")
            metrics = {
                "source_file_type": "csv",
                "extracted_from_archive": False,
                "converted_to_csv": True,
                "archive_member_name": None,
                "raw_row_count": raw_row_count,
                "normalized_row_count": int(len(df.index)),
                "source_bytes": len(payload),
                "normalized_bytes": len(csv_payload),
            }
            return [
                (Path(source_name).name, csv_payload, _sha256(csv_payload), metrics)
            ]

        metrics = {
            "source_file_type": "csv",
            "extracted_from_archive": False,
            "converted_to_csv": False,
            "archive_member_name": None,
            "raw_row_count": _count_csv_rows(payload),
            "normalized_row_count": _count_csv_rows(payload),
            "source_bytes": len(payload),
            "normalized_bytes": len(payload),
        }
        return [(Path(source_name).name, payload, content_hash, metrics)]

    if lowered.endswith(".zip"):
        outputs = []
        for name, csv_payload, metrics in _all_csvs_from_zip(payload, target):
            outputs.append(
                (
                    name,
                    csv_payload,
                    _sha256(csv_payload),  # per-file hash for uniqueness
                    {
                        **metrics,
                        "source_bytes": len(payload),
                        "normalized_bytes": len(csv_payload),
                    },
                )
            )
        return outputs

    if lowered.endswith(".xlsx") or lowered.endswith(".xls"):
        ext = Path(source_name).suffix.lower() or ".xlsx"
        sheet_outputs = _excel_to_csv(Path(source_name).stem, payload, ext, target)
        return _finalize_spreadsheet_outputs(sheet_outputs, payload, content_hash)

    if lowered.endswith(".ods"):
        ext = Path(source_name).suffix.lower() or ".ods"
        sheet_outputs = _ods_to_csv(Path(source_name).stem, payload, ext, target)
        return _finalize_spreadsheet_outputs(sheet_outputs, payload, content_hash)

    raise ValueError(f"Unsupported file type for source: {source_name}")


def build_artifact(
    source,
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
        subject_period_hint=source.subject_period_hint,
        link_text=source.link_text,
        source_url=source.source_url,
        page_text=source.page_text,
        duration_type_hint=(
            source.period_coverage_hint.file_scope.duration_type
            if source.period_coverage_hint
            else "unknown"
        ),
        duration_value_hint=(
            source.period_coverage_hint.file_scope.duration_value
            if source.period_coverage_hint
            else None
        ),
        duration_unit_hint=(
            source.period_coverage_hint.file_scope.duration_unit
            if source.period_coverage_hint
            else None
        ),
        fiscal_year_start_month_hint=(
            source.period_coverage_hint.file_scope.fiscal_year_start_month
            if source.period_coverage_hint
            else None
        ),
    )
    adls_path_prefix = (
        source.adls_path_prefix or f"{source.series_id}/{source.sub_dataset_id}"
    )
    return LoadArtifact(
        adls_path=_adls_path(
            adls_path_prefix,
            downloaded_at,
            filename,
        ),
        source_url=source.source_url,
        series_id=source.series_id,
        sub_dataset_id=source.sub_dataset_id,
        subject_period_from=coverage.subject_period_from,
        subject_period_to=coverage.subject_period_to,
        subject_period_coverage_type=coverage.coverage_type,
        subject_period_inference_method=coverage.inference_method,
        subject_period_inference_source=coverage.inference_source,
        subject_period_inference_confidence=coverage.confidence,
        file_scope_duration_type=(
            source.period_coverage_hint.file_scope.duration_type
            if source.period_coverage_hint
            else "unknown"
        ),
        file_scope_duration_value=(
            source.period_coverage_hint.file_scope.duration_value
            if source.period_coverage_hint
            else None
        ),
        file_scope_duration_unit=(
            source.period_coverage_hint.file_scope.duration_unit
            if source.period_coverage_hint
            and source.period_coverage_hint.file_scope.duration_unit
            else ""
        ),
        file_scope_fiscal_year_start_month=(
            source.period_coverage_hint.file_scope.fiscal_year_start_month
            if source.period_coverage_hint
            else None
        ),
        breakdown_granularity=(
            source.period_coverage_hint.breakdown_granularity
            if source.period_coverage_hint
            else []
        ),
        publication_date=source.publication_date_value or "",
        source_content_hash=content_hash,
        acquisition_method=acquisition_method,
        fallback_reason=fallback_reason,
        downloaded_at=downloaded_at,
        adls_path_prefix=adls_path_prefix,
    )


def normalize_local_file_to_csv(
    local_file: Path,
    target: Optional[TargetConfig] = None,
) -> List[Tuple[str, bytes, str, Dict[str, Any]]]:
    """Normalize a local file to CSV, returning filename, content, hash, and metrics."""
    payload = local_file.read_bytes()
    return normalize_payload_to_csv(local_file.name, payload, target)


def ensure_utf8(file_path: Path) -> None:
    """
    Ensure a CSV file is UTF-8 encoded in-place.
    Falls back to CP1252 if UTF-8 decoding fails.
    """
    raw = file_path.read_bytes()

    try:
        raw.decode("utf-8")
        return  # already valid UTF-8
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
        file_path.write_text(text, encoding="utf-8")
