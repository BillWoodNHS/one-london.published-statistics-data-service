from __future__ import annotations

import datetime
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
from .settings import MIN_PLAUSIBLE_PUBLICATION_DATE

CONTRACT_VERSION = "1.2.0"


def _manifest_root() -> Path:
    configured = Path(os.environ.get("MANIFEST_ROOT", "../config/datasets"))
    if configured.is_absolute():
        return configured

    return (Path(__file__).resolve().parents[2] / configured).resolve()


def _manual_prefix() -> str:
    return os.environ.get("MANUAL_INPUT_PREFIX", "manual").strip("/")


def _telemetry_prefix() -> str:
    return os.environ.get("TELEMETRY_PREFIX", "_telemetry/function_app_events").strip(
        "/"
    )


def _new_run_id() -> str:
    return uuid.uuid4().hex


def _event_timestamp() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def _emit_event(events: List[Dict[str, Any]], **fields: Any) -> None:
    event: Dict[str, Any] = {
        "event_timestamp_utc": _event_timestamp(),
        "contract_version": CONTRACT_VERSION,
    }
    event.update(fields)
    events.append(event)


def _write_telemetry_events(run_id: str, events: List[Dict[str, Any]]) -> str:
    day_partition = datetime.datetime.utcnow().strftime("%Y%m%d")
    path = f"{_telemetry_prefix()}/event_date={day_partition}/run_id={run_id}.jsonl"
    payload = b"\n".join(
        json.dumps(event, separators=(",", ":")).encode("utf-8") for event in events
    )
    upload_bytes(path, payload + b"\n")
    return path


def _audit_payload(
    artifact: LoadArtifact,
    source_etag: Optional[str] = None,
    source_last_modified: Optional[str] = None,
) -> Dict[str, Any]:
    ingested_at = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    pub_date = artifact.publication_date
    pub_date_source = "scraped" if pub_date else "none"
    # _PAYLOAD_STAGE_PATH: stage-relative path used as JOIN key with _SOURCE_FILE_PATH
    payload_stage_path = artifact.adls_path.replace(
        artifact.adls_path_prefix + "/", "", 1
    )
    payload: Dict[str, Any] = {
        "_CONTRACT_VERSION": CONTRACT_VERSION,
        "_DOWNLOADED_AT": artifact.downloaded_at,
        "_INGESTED_AT": ingested_at,
        "_SOURCE_FILE_PATH": artifact.source_url,
        "_SOURCE_FILE_NAME": artifact.adls_path.split("/")[-1],
        "_FILE_CONTENT_KEY": artifact.source_content_hash,
        "_SUBJECT_PERIOD_FROM": artifact.subject_period_from,
        "_SUBJECT_PERIOD_TO": artifact.subject_period_to,
        "_SUBJECT_PERIOD_COVERAGE_TYPE": artifact.subject_period_coverage_type,
        "_SUBJECT_PERIOD_INFERENCE_METHOD": artifact.subject_period_inference_method,
        "_SUBJECT_PERIOD_INFERENCE_SOURCE": artifact.subject_period_inference_source,
        "_SUBJECT_PERIOD_INFERENCE_CONFIDENCE": artifact.subject_period_inference_confidence,
        "_FILE_SCOPE_DURATION_TYPE": artifact.file_scope_duration_type,
        "_FILE_SCOPE_DURATION_VALUE": (
            str(artifact.file_scope_duration_value)
            if artifact.file_scope_duration_value is not None
            else ""
        ),
        "_FILE_SCOPE_DURATION_UNIT": artifact.file_scope_duration_unit,
        "_FILE_SCOPE_FISCAL_YEAR_START_MONTH": (
            str(artifact.file_scope_fiscal_year_start_month)
            if artifact.file_scope_fiscal_year_start_month is not None
            else ""
        ),
        "_BREAKDOWN_GRANULARITY": ",".join(artifact.breakdown_granularity),
        "period_coverage": {
            "file_scope": {
                "duration_type": artifact.file_scope_duration_type,
                "duration_value": artifact.file_scope_duration_value,
                "duration_unit": artifact.file_scope_duration_unit,
                "fiscal_year_start_month": artifact.file_scope_fiscal_year_start_month,
            },
            "breakdown_granularity": artifact.breakdown_granularity,
        },
        "_PUBLICATION_DATE": pub_date,
        "_PUBLICATION_DATE_SOURCE": pub_date_source,
        "_ACQUISITION_METHOD": artifact.acquisition_method,
        "_FALLBACK_REASON": artifact.fallback_reason,
        "_LOAD_ID": artifact.source_content_hash[:16],
        "_SERIES_ID": artifact.series_id,
        "_SUB_DATASET_ID": artifact.sub_dataset_id,
        "_TARGET_PATH": artifact.adls_path,
        "_PAYLOAD_STAGE_PATH": payload_stage_path,
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
) -> Dict[str, Any]:
    audit_path = artifact.adls_path.rsplit("/", 1)[0] + "/_INGEST_METADATA.json"
    record = _audit_payload(artifact, source_etag, source_last_modified)
    payload = json.dumps(record, indent=2).encode("utf-8")

    upload_bytes(audit_path, payload)
    return record


def _load_sidecar_records(series_id: str, sub_dataset_id: str) -> List[Dict[str, Any]]:
    prefix = f"{series_id}/{sub_dataset_id}/"
    metadata_paths = [
        path
        for path in list_blob_paths(prefix)
        if path.endswith("/_INGEST_METADATA.json")
    ]

    records: List[Dict[str, Any]] = []
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
    records: List[Dict[str, Any]], source_url: str
) -> Optional[Dict[str, Any]]:
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
    latest_record: Optional[Dict[str, Any]],
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
    """Return a clean publication date if it passes plausibility checks.

    Returns the date string as-is when it meets MIN_PLAUSIBLE_PUBLICATION_DATE.
    Missing or implausible dates return empty string; the sidecar metadata
    will record _PUBLICATION_DATE_SOURCE as 'none' in those cases.
    """
    if value and value >= MIN_PLAUSIBLE_PUBLICATION_DATE:
        return value
    return ""


def execute_ingestion() -> Dict[str, Any]:
    manifest_root = _manifest_root()
    manual_prefix = _manual_prefix()
    run_id = _new_run_id()
    telemetry_events: List[Dict[str, Any]] = []
    configs = load_manifests(manifest_root)
    uploaded_paths: List[str] = []

    for config in configs:
        sidecar_cache: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

        def _records_for(series_id: str, sub_dataset_id: str) -> List[Dict[str, Any]]:
            key = (series_id, sub_dataset_id)
            if key not in sidecar_cache:
                sidecar_cache[key] = _load_sidecar_records(series_id, sub_dataset_id)
            return sidecar_cache[key]

        effective_manual_prefix = (
            config.fallback.manual_drop_path.strip("/")
            if config.fallback.manual_drop_path
            else manual_prefix
        )
        _emit_event(
            telemetry_events,
            run_id=run_id,
            stage="SCAN",
            status="STARTED",
            attempt_number=1,
            series_id=config.series_id,
            sub_dataset_id=None,
            source_url=config.entry_url,
        )
        scan_started = time.perf_counter()
        discovered = discover_files(config)
        _emit_event(
            telemetry_events,
            run_id=run_id,
            stage="SCAN",
            status="SUCCEEDED",
            attempt_number=1,
            series_id=config.series_id,
            sub_dataset_id=None,
            source_url=config.entry_url,
            discovered_file_count=len(discovered),
            duration_ms=int((time.perf_counter() - scan_started) * 1000),
        )
        discovered_targets = {item.sub_dataset_id for item in discovered}

        for item in discovered:
            records = _records_for(item.series_id, item.sub_dataset_id)
            latest = _latest_record_for_source(records, item.source_url)
            source_etag, source_last_modified = _get_source_headers(item.source_url)
            if _skip_download_from_headers(latest, source_etag, source_last_modified):
                _emit_event(
                    telemetry_events,
                    run_id=run_id,
                    stage="DOWNLOAD",
                    status="SKIPPED",
                    attempt_number=1,
                    series_id=item.series_id,
                    sub_dataset_id=item.sub_dataset_id,
                    source_url=item.source_url,
                    skip_reason="source_unchanged",
                )
                logging.info("Skipped download (source unchanged): %s", item.source_url)
                continue

            _emit_event(
                telemetry_events,
                run_id=run_id,
                stage="DOWNLOAD",
                status="STARTED",
                attempt_number=1,
                series_id=item.series_id,
                sub_dataset_id=item.sub_dataset_id,
                source_url=item.source_url,
            )
            download_started = time.perf_counter()
            try:
                filename, csv_payload, content_hash, normalize_metrics = (
                    normalize_to_csv(item.source_url)
                )
            except Exception as ex:
                _emit_event(
                    telemetry_events,
                    run_id=run_id,
                    stage="DOWNLOAD",
                    status="FAILED",
                    attempt_number=1,
                    series_id=item.series_id,
                    sub_dataset_id=item.sub_dataset_id,
                    source_url=item.source_url,
                    error_type=type(ex).__name__,
                    error_message=str(ex),
                    duration_ms=int((time.perf_counter() - download_started) * 1000),
                )
                raise

            _emit_event(
                telemetry_events,
                run_id=run_id,
                stage="DOWNLOAD",
                status="SUCCEEDED",
                attempt_number=1,
                series_id=item.series_id,
                sub_dataset_id=item.sub_dataset_id,
                source_url=item.source_url,
                source_bytes=normalize_metrics.get("source_bytes"),
                duration_ms=int((time.perf_counter() - download_started) * 1000),
            )

            if normalize_metrics.get("extracted_from_archive"):
                _emit_event(
                    telemetry_events,
                    run_id=run_id,
                    stage="EXTRACT",
                    status="SUCCEEDED",
                    attempt_number=1,
                    series_id=item.series_id,
                    sub_dataset_id=item.sub_dataset_id,
                    source_url=item.source_url,
                    file_name=normalize_metrics.get("archive_member_name"),
                )

            _emit_event(
                telemetry_events,
                run_id=run_id,
                stage="NORMALIZE",
                status="SUCCEEDED",
                attempt_number=1,
                series_id=item.series_id,
                sub_dataset_id=item.sub_dataset_id,
                source_url=item.source_url,
                file_name=filename,
                raw_row_count=normalize_metrics.get("raw_row_count"),
                normalized_row_count=normalize_metrics.get("normalized_row_count"),
                normalized_bytes=normalize_metrics.get("normalized_bytes"),
            )

            if latest and latest.get("_FILE_CONTENT_KEY") == content_hash:
                _emit_event(
                    telemetry_events,
                    run_id=run_id,
                    stage="UPLOAD",
                    status="SKIPPED",
                    attempt_number=1,
                    series_id=item.series_id,
                    sub_dataset_id=item.sub_dataset_id,
                    source_url=item.source_url,
                    source_content_hash=content_hash,
                    skip_reason="content_unchanged",
                )
                logging.info("Skipped upload (content unchanged): %s", item.source_url)
                continue

            item.publication_date_value = _resolve_publication_datetime(
                item.publication_date_value
            )
            downloaded_at = now_utc_compact()
            artifact = build_artifact(
                item,
                filename,
                content_hash,
                downloaded_at,
                acquisition_method="automated",
            )
            upload_bytes(artifact.adls_path, csv_payload)
            record = _write_audit_record(artifact, source_etag, source_last_modified)
            _emit_event(
                telemetry_events,
                run_id=run_id,
                stage="UPLOAD",
                status="SUCCEEDED",
                attempt_number=1,
                series_id=item.series_id,
                sub_dataset_id=item.sub_dataset_id,
                source_url=item.source_url,
                file_name=filename,
                source_content_hash=content_hash,
                load_id=artifact.source_content_hash[:16],
                raw_row_count=normalize_metrics.get("raw_row_count"),
                normalized_row_count=normalize_metrics.get("normalized_row_count"),
                uploaded_path=artifact.adls_path,
            )
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
                filename, csv_payload, content_hash, normalize_metrics = (
                    normalize_payload_to_csv(candidate.link_text, payload)
                )
                normalize_metrics["source_bytes"] = len(payload)
                _emit_event(
                    telemetry_events,
                    run_id=run_id,
                    stage="NORMALIZE",
                    status="SUCCEEDED",
                    attempt_number=1,
                    series_id=candidate.series_id,
                    sub_dataset_id=candidate.sub_dataset_id,
                    source_url=candidate.source_url,
                    file_name=filename,
                    raw_row_count=normalize_metrics.get("raw_row_count"),
                    normalized_row_count=normalize_metrics.get("normalized_row_count"),
                    normalized_bytes=normalize_metrics.get("normalized_bytes"),
                    source_bytes=normalize_metrics.get("source_bytes"),
                    acquisition_method="manual",
                )
                if latest and latest.get("_FILE_CONTENT_KEY") == content_hash:
                    _emit_event(
                        telemetry_events,
                        run_id=run_id,
                        stage="UPLOAD",
                        status="SKIPPED",
                        attempt_number=1,
                        series_id=candidate.series_id,
                        sub_dataset_id=candidate.sub_dataset_id,
                        source_url=candidate.source_url,
                        source_content_hash=content_hash,
                        skip_reason="content_unchanged",
                        acquisition_method="manual",
                    )
                    logging.info(
                        "Skipped manual upload (content unchanged): %s",
                        candidate.source_url,
                    )
                    continue

                candidate.publication_date_value = _resolve_publication_datetime(
                    candidate.publication_date_value
                )
                downloaded_at = now_utc_compact()
                artifact = build_artifact(
                    candidate,
                    filename,
                    content_hash,
                    downloaded_at,
                    acquisition_method="manual",
                    fallback_reason="auto_discovery_empty",
                )
                upload_bytes(artifact.adls_path, csv_payload)
                record = _write_audit_record(artifact)
                _emit_event(
                    telemetry_events,
                    run_id=run_id,
                    stage="UPLOAD",
                    status="SUCCEEDED",
                    attempt_number=1,
                    series_id=candidate.series_id,
                    sub_dataset_id=candidate.sub_dataset_id,
                    source_url=candidate.source_url,
                    file_name=filename,
                    source_content_hash=content_hash,
                    load_id=artifact.source_content_hash[:16],
                    raw_row_count=normalize_metrics.get("raw_row_count"),
                    normalized_row_count=normalize_metrics.get("normalized_row_count"),
                    uploaded_path=artifact.adls_path,
                    acquisition_method="manual",
                )
                uploaded_paths.append(artifact.adls_path)
                records.append(record)
                logging.info("Uploaded manual file %s", artifact.adls_path)

    telemetry_path = _write_telemetry_events(run_id, telemetry_events)
    return {
        "uploaded": uploaded_paths,
        "run_id": run_id,
        "telemetry_path": telemetry_path,
    }
