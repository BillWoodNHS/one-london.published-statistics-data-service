"""Local-only schema drift detection for the DuckDB end-to-end simulation.

Compares the columns actually present in a downloaded CSV against a known
column list declared in config/schemas/<dataset_id>.yaml, and flags drift
as a warning (never a load failure) when it exceeds a configurable Jaccard
distance threshold. This module is only ever invoked from tools/local_dev/
and must not be imported by function_app/src/.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class KnownSchema:
    """Known column list for one object_name_suffix in a dataset."""

    object_name_suffix: str
    columns: list[str]


@dataclass
class SchemaDriftWarning:
    """Describes a single drift detection above the configured threshold."""

    table_name: str
    csv_path: Path
    known_columns: list[str]
    actual_columns: list[str]
    drift_ratio: float


def load_known_schema(
    schema_root: Path, dataset_id: str, suffix: str
) -> KnownSchema | None:
    """Load the known column list for one suffix from its dataset schema file."""
    schema_path = schema_root / f"{dataset_id}.yaml"
    if not schema_path.exists():
        return None
    raw = yaml.safe_load(schema_path.read_text(encoding="utf-8")) or {}
    entry = (raw.get("schemas") or {}).get(suffix)
    if not entry or not entry.get("columns"):
        return None
    return KnownSchema(object_name_suffix=suffix, columns=list(entry["columns"]))


def _jaccard_distance(known: set[str], actual: set[str]) -> float:
    """Compute 1 - |intersection| / |union| between two column sets."""
    union = known | actual
    if not union:
        return 0.0
    intersection = known & actual
    return 1.0 - len(intersection) / len(union)


def detect_drift(
    known: KnownSchema, actual_columns: list[str], threshold: float
) -> SchemaDriftWarning | None:
    """Return a SchemaDriftWarning when drift exceeds threshold, else None.

    The returned warning's csv_path is left unset (Path()) - callers that
    have the originating file path should set it before reporting.
    """
    distance = _jaccard_distance(set(known.columns), set(actual_columns))
    if distance <= threshold:
        return None
    return SchemaDriftWarning(
        table_name=known.object_name_suffix,
        csv_path=Path(),
        known_columns=known.columns,
        actual_columns=actual_columns,
        drift_ratio=distance,
    )


def warnings_to_json(warnings: list[SchemaDriftWarning]) -> list[dict[str, Any]]:
    """Serialize drift warnings to JSON-compatible dicts."""
    return [
        {
            "table_name": warning.table_name,
            "csv_path": str(warning.csv_path),
            "known_columns": warning.known_columns,
            "actual_columns": warning.actual_columns,
            "drift_ratio": warning.drift_ratio,
        }
        for warning in warnings
    ]
