from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from .adls_writer import download_blob_bytes, list_blob_paths, upload_bytes
from .datetime_utils import now_utc_compact
from .download_and_normalize import (
    build_artifact,
    normalize_payload_to_csv,
    normalize_to_csv,
)
from .manifest_loader import load_manifests
from .manual_sources import discover_manual_files
from .models import LoadArtifact
from .scraper import discover_files

CONTRACT_VERSION = "1.0.0"


def _manifest_root() -> Path:
    configured = Path(os.environ.get("MANIFEST_ROOT", "../config/datasets"))
    if configured.is_absolute():
        return configured

    return (Path(__file__).resolve().parents[2] / configured).resolve()


def _manual_prefix() -> str:
    return os.environ.get("MANUAL_INPUT_PREFIX", "manual").strip("/")


def _audit_payload(
    artifact: LoadArtifact,
    source_etag: Optional[str] = None,
    source_last_modified: Optional[str] = None,
) -> Dict[str, str]:
    ingested_at = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    payload: Dict[str, str] = {
        "_CONTRACT_VERSION": CONTRACT_VERSION,
        "_INGESTED_AT": ingested_at,
        "_SOURCE_FILE_PATH": artifact.source_url,
        "_SOURCE_FILE_NAME": artifact.adls_path.split("/")[-1],
        "_FILE_CONTENT_KEY": artifact.source_content_hash,
        "_SUBJECT_PERIOD": artifact.subject_period,
        "_PUBLICATION_DATE": artifact.publication_date,
        "_ACQUISITION_METHOD": artifact.acquisition_method,
        "_FALLBACK_REASON": artifact.fallback_reason,
        "_LOAD_ID": artifact.source_content_hash[:16],
        "_SERIES_ID": artifact.series_id,
        "_SUB_DATASET_ID": artifact.sub_dataset_id,
        "_TARGET_PATH": artifact.adls_path,
    }
    if source_etag:
        payload["_SOURCE_ETAG"] = source_etag
    if source_last_modified:
        payload["_SOURCE_LAST_MODIFIED"] = source_last_modified
    return payload


def _write_audit_record(
    artifact: LoadArtifact,
    source_etag: Optional[str] = None,
    source_last_modified: Optional[str] = None,
) -> Dict[str, str]:
    audit_path = artifact.adls_path.rsplit("/", 1)[0] + "/_INGEST_METADATA.json"
    record = _audit_payload(artifact, source_etag, source_last_modified)
    payload = json.dumps(record, indent=2).encode("utf-8")

    upload_bytes(audit_path, payload)
    return record


def _load_sidecar_records(series_id: str, sub_dataset_id: str) -> List[Dict[str, str]]:
    prefix = f"{series_id}/{sub_dataset_id}/"
    metadata_paths = [
        path
        for path in list_blob_paths(prefix)
        if path.endswith("/_INGEST_METADATA.json")
    ]

    records: List[Dict[str, str]] = []
    for metadata_path in metadata_paths:
        try:
            payload = download_blob_bytes(metadata_path)
            data = json.loads(payload.decode("utf-8"))
            if isinstance(data, dict):
                records.append(data)
        except Exception:
            logging.warning("Skipping unreadable sidecar metadata at %s", metadata_path)

    return records


def _latest_record_for_source(
    records: List[Dict[str, str]], source_url: str
) -> Optional[Dict[str, str]]:
    matches = [
        record for record in records if record.get("_SOURCE_FILE_PATH") == source_url
    ]
    if not matches:
        return None
    return max(matches, key=lambda record: record.get("_INGESTED_AT", ""))


def _get_source_headers(source_url: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        response = requests.head(source_url, timeout=30, allow_redirects=True)
        if response.status_code >= 400:
            return None, None
        etag = response.headers.get("ETag")
        if etag:
            etag = etag.strip('"')
        last_modified = response.headers.get("Last-Modified")
        return etag, last_modified
    except Exception:
        return None, None


def _skip_download_from_headers(
    latest_record: Optional[Dict[str, str]],
    source_etag: Optional[str],
    source_last_modified: Optional[str],
) -> bool:
    if not latest_record:
        return False

    previous_etag = latest_record.get("_SOURCE_ETAG")
    if source_etag and previous_etag and source_etag == previous_etag:
        return True

    previous_last_modified = latest_record.get("_SOURCE_LAST_MODIFIED")
    if (
        source_last_modified
        and previous_last_modified
        and source_last_modified == previous_last_modified
    ):
        return True

    return False


def _resolve_publication_datetime(value: Optional[str]) -> str:
    return value or now_utc_compact()


def execute_ingestion() -> Dict[str, List[str]]:
    manifest_root = _manifest_root()
    manual_prefix = _manual_prefix()
    configs = load_manifests(manifest_root)
    uploaded_paths: List[str] = []

    for config in configs:
        sidecar_cache: Dict[Tuple[str, str], List[Dict[str, str]]] = {}

        def _records_for(series_id: str, sub_dataset_id: str) -> List[Dict[str, str]]:
            key = (series_id, sub_dataset_id)
            if key not in sidecar_cache:
                sidecar_cache[key] = _load_sidecar_records(series_id, sub_dataset_id)
            return sidecar_cache[key]

        effective_manual_prefix = (
            config.fallback.manual_drop_path.strip("/")
            if config.fallback.manual_drop_path
            else manual_prefix
        )
        discovered = discover_files(config)
        discovered_targets = {item.sub_dataset_id for item in discovered}

        for item in discovered:
            records = _records_for(item.series_id, item.sub_dataset_id)
            latest = _latest_record_for_source(records, item.source_url)
            source_etag, source_last_modified = _get_source_headers(item.source_url)
            if _skip_download_from_headers(latest, source_etag, source_last_modified):
                logging.info("Skipped download (source unchanged): %s", item.source_url)
                continue

            filename, csv_payload, content_hash = normalize_to_csv(item.source_url)
            if latest and latest.get("_FILE_CONTENT_KEY") == content_hash:
                logging.info("Skipped upload (content unchanged): %s", item.source_url)
                continue

            item.publication_date_value = _resolve_publication_datetime(
                item.publication_date_value
            )
            artifact = build_artifact(
                item, filename, content_hash, acquisition_method="automated"
            )
            upload_bytes(artifact.adls_path, csv_payload)
            record = _write_audit_record(artifact, source_etag, source_last_modified)
            uploaded_paths.append(artifact.adls_path)
            records.append(record)
            logging.info("Uploaded %s", artifact.adls_path)

        if not config.fallback.allow_manual_acquisition:
            continue

        for target in config.targets:
            if target.sub_dataset_id in discovered_targets:
                continue

            manual_candidates = discover_manual_files(
                config, target, effective_manual_prefix
            )
            for candidate in manual_candidates:
                records = _records_for(candidate.series_id, candidate.sub_dataset_id)
                latest = _latest_record_for_source(records, candidate.source_url)
                payload = download_blob_bytes(candidate.source_url)
                filename, csv_payload, content_hash = normalize_payload_to_csv(
                    candidate.link_text, payload
                )
                if latest and latest.get("_FILE_CONTENT_KEY") == content_hash:
                    logging.info(
                        "Skipped manual upload (content unchanged): %s",
                        candidate.source_url,
                    )
                    continue

                candidate.publication_date_value = _resolve_publication_datetime(
                    candidate.publication_date_value
                )
                artifact = build_artifact(
                    candidate,
                    filename,
                    content_hash,
                    acquisition_method="manual",
                    fallback_reason="auto_discovery_empty",
                )
                upload_bytes(artifact.adls_path, csv_payload)
                record = _write_audit_record(artifact)
                uploaded_paths.append(artifact.adls_path)
                records.append(record)
                logging.info("Uploaded manual file %s", artifact.adls_path)

    return {"uploaded": uploaded_paths}
