from __future__ import annotations

import os
from pathlib import Path
from typing import List


def _local_mode() -> bool:
    """Return True if running in local storage mode, based on environment variable."""
    return os.environ.get("LOCAL_STORAGE_MODE", "false").lower() in {"1", "true", "yes"}


def _local_root() -> Path:
    """Return the root path for local storage, resolved from environment or default."""
    configured = os.environ.get("LOCAL_STORAGE_ROOT", ".local_adls")
    return Path(configured).resolve()


def _account_url() -> str:
    """Return the ADLS account URL from environment variable."""
    return os.environ["ADLS_ACCOUNT_URL"]


def _container_name() -> str:
    """Return the ADLS container name from environment variable."""
    return os.environ["ADLS_CONTAINER"]


def _default_prefix() -> str:
    """Return the ADLS prefix from environment variable, with slashes stripped."""
    return os.environ.get("ADLS_PREFIX", "").strip("/")


def _container_client():
    """Return an Azure ContainerClient for the configured ADLS account and container."""
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import ContainerClient

    return ContainerClient(
        account_url=_account_url(),
        container_name=_container_name(),
        credential=DefaultAzureCredential(),
    )


def _join_prefix(prefix: str, path_in_container: str) -> str:
    """Join a prefix and path for blob storage, ensuring proper formatting."""
    cleaned = path_in_container.strip("/")
    if not prefix:
        return cleaned
    if not cleaned:
        return prefix
    return f"{prefix}/{cleaned}"


def upload_bytes(path_in_container: str, payload: bytes) -> None:
    """Upload bytes to the given path in ADLS or local storage.

    Creates parent directories as needed in local mode.
    """
    if _local_mode():
        local_path = _local_root() / path_in_container.strip("/")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(payload)
        return

    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobClient

    account_url = _account_url()
    container = _container_name()
    prefix = _default_prefix()

    blob_path = _join_prefix(prefix, path_in_container)

    client = BlobClient(
        account_url=account_url,
        container_name=container,
        blob_name=blob_path,
        credential=DefaultAzureCredential(),
    )
    client.upload_blob(payload, overwrite=True)


def list_blob_paths(prefix: str) -> List[str]:
    """List all blob paths under the given prefix in ADLS or local storage."""
    if _local_mode():
        root = _local_root()
        wanted_prefix = prefix.strip("/")
        if not root.exists():
            return []

        results: List[str] = []
        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(root).as_posix()
            if rel.startswith(wanted_prefix):
                results.append(rel)
        return results

    client = _container_client()
    return [blob.name for blob in client.list_blobs(name_starts_with=prefix)]


def download_blob_bytes(blob_path: str) -> bytes:
    """Download bytes from the given blob path in ADLS or local storage."""
    if _local_mode():
        local_path = _local_root() / blob_path.strip("/")
        return local_path.read_bytes()

    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobClient

    client = BlobClient(
        account_url=_account_url(),
        container_name=_container_name(),
        blob_name=blob_path,
        credential=DefaultAzureCredential(),
    )
    return client.download_blob().readall()
