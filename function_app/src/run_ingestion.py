from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List

from .adls_writer import download_blob_bytes, upload_bytes
from .download_and_normalize import (
    build_artifact,
    normalize_payload_to_csv,
    normalize_to_csv,
)
from .manifest_loader import load_manifests
from .manual_sources import discover_manual_files
from .models import LoadArtifact
from .scraper import discover_files


def _manifest_root() -> Path:
    configured = Path(os.environ.get("MANIFEST_ROOT", "../config/datasets"))
    if configured.is_absolute():
        return configured

    return (Path(__file__).resolve().parents[2] / configured).resolve()


def _manual_prefix() -> str:
    return os.environ.get("MANUAL_INPUT_PREFIX", "manual").strip("/")


def _write_audit_record(artifact: LoadArtifact) -> None:
    audit_path = artifact.adls_path.rsplit("/", 1)[0] + "/_INGEST_METADATA.json"
    payload = json.dumps(
        {
            "_INGESTED_AT": __import__("datetime")
            .datetime.utcnow()
            .isoformat(timespec="seconds")
            + "Z",
            "_SOURCE_FILE_PATH": artifact.source_url,
            "_SOURCE_FILE_NAME": artifact.adls_path.split("/")[-1],
            "_FILE_CONTENT_KEY": artifact.source_content_hash,
            "_PUBLICATION_DATE": artifact.publication_date,
            "_ACQUISITION_METHOD": artifact.acquisition_method,
            "_FALLBACK_REASON": artifact.fallback_reason,
            "_LOAD_ID": artifact.source_content_hash[:16],
            "_SERIES_ID": artifact.series_id,
            "_SUB_DATASET_ID": artifact.sub_dataset_id,
            "_TARGET_PATH": artifact.adls_path,
        },
        indent=2,
    ).encode("utf-8")

    upload_bytes(audit_path, payload)


def execute_ingestion() -> Dict[str, List[str]]:
    manifest_root = _manifest_root()
    manual_prefix = _manual_prefix()
    configs = load_manifests(manifest_root)
    uploaded_paths: List[str] = []

    for config in configs:
        effective_manual_prefix = (
            config.fallback.manual_drop_path.strip("/")
            if config.fallback.manual_drop_path
            else manual_prefix
        )
        discovered = discover_files(config)
        discovered_targets = {item.sub_dataset_id for item in discovered}

        for item in discovered:
            filename, csv_payload, content_hash = normalize_to_csv(item.source_url)
            artifact = build_artifact(
                item, filename, content_hash, acquisition_method="automated"
            )
            upload_bytes(artifact.adls_path, csv_payload)
            _write_audit_record(artifact)
            uploaded_paths.append(artifact.adls_path)
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
                payload = download_blob_bytes(candidate.source_url)
                filename, csv_payload, content_hash = normalize_payload_to_csv(
                    candidate.link_text, payload
                )
                artifact = build_artifact(
                    candidate,
                    filename,
                    content_hash,
                    acquisition_method="manual",
                    fallback_reason="auto_discovery_empty",
                )
                upload_bytes(artifact.adls_path, csv_payload)
                _write_audit_record(artifact)
                uploaded_paths.append(artifact.adls_path)
                logging.info("Uploaded manual file %s", artifact.adls_path)

    return {"uploaded": uploaded_paths}
