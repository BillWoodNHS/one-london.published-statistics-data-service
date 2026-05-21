from __future__ import annotations

import csv
import hashlib
import io
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Tuple

import pandas as pd
import requests

from .models import DiscoveredFile, LoadArtifact


def _to_iso_partition_value(raw_value: str) -> str:
    value = raw_value.strip().replace(" ", "-").replace("/", "-").replace(":", "")
    return value


def _adls_path(series_id: str, sub_dataset_id: str, publication_date: str, filename: str) -> str:
    safe_pub = _to_iso_partition_value(publication_date)
    return f"{series_id}/{sub_dataset_id}/publication_date={safe_pub}/{filename}"


def _download(url: str) -> bytes:
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.content


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _first_csv_from_zip(payload: bytes) -> Tuple[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        for name in zf.namelist():
            if name.lower().endswith(".csv"):
                return Path(name).name, zf.read(name)

        for name in zf.namelist():
            if name.lower().endswith((".xlsx", ".xls")):
                data = zf.read(name)
                ext = Path(name).suffix.lower() or ".xlsx"
                return _excel_to_csv(Path(name).stem, data, ext)

    raise ValueError("ZIP did not contain CSV or Excel files")


def _excel_to_csv(base_name: str, payload: bytes, extension: str = ".xlsx") -> Tuple[str, bytes]:
    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp:
        tmp.write(payload)
        tmp_path = tmp.name

    try:
        df = pd.read_excel(tmp_path)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(df.columns.tolist())
        writer.writerows(df.values.tolist())
        return f"{base_name}.csv", buffer.getvalue().encode("utf-8")
    finally:
        os.unlink(tmp_path)


def normalize_to_csv(file_url: str) -> Tuple[str, bytes, str]:
    payload = _download(file_url)
    return normalize_payload_to_csv(Path(file_url).name, payload)


def normalize_payload_to_csv(source_name: str, payload: bytes) -> Tuple[str, bytes, str]:
    content_hash = _sha256(payload)
    lowered = source_name.lower()

    if lowered.endswith(".csv"):
        return Path(source_name).name, payload, content_hash

    if lowered.endswith(".zip"):
        name, csv_payload = _first_csv_from_zip(payload)
        return name, csv_payload, content_hash

    if lowered.endswith(".xlsx") or lowered.endswith(".xls"):
        ext = Path(source_name).suffix.lower() or ".xlsx"
        name, csv_payload = _excel_to_csv(Path(source_name).stem, payload, ext)
        return name, csv_payload, content_hash

    raise ValueError(f"Unsupported file type for source: {source_name}")


def build_artifact(file: DiscoveredFile, filename: str, content_hash: str, acquisition_method: str = "automated", fallback_reason: str = "") -> LoadArtifact:
    return LoadArtifact(
        adls_path=_adls_path(file.series_id, file.sub_dataset_id, file.publication_date_value, filename),
        source_url=file.source_url,
        series_id=file.series_id,
        sub_dataset_id=file.sub_dataset_id,
        publication_date=file.publication_date_value,
        source_content_hash=content_hash,
        acquisition_method=acquisition_method,
        fallback_reason=fallback_reason,
    )


def normalize_local_file_to_csv(local_file: Path) -> Tuple[str, bytes, str]:
    payload = local_file.read_bytes()
    return normalize_payload_to_csv(local_file.name, payload)
