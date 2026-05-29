from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from urllib.parse import urlparse


@dataclass
class InventoryRow:
    dataset_name: str
    parent_link: str
    sub_link: str
    sub_collection: str
    target_file: str
    note: str


@dataclass
class Sample:
    file_url: str
    notes: str = ""


def _norm(value: str) -> str:
    return "".join(ch for ch in (value or "").lower().strip() if ch.isalnum())


def _pick_header(headers: Sequence[str], *candidates: str) -> Optional[str]:
    mapping = {_norm(h): h for h in headers}
    for candidate in candidates:
        hit = mapping.get(_norm(candidate))
        if hit:
            return hit
    return None


def _slugify(value: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return lowered or "unknown-dataset"


def _is_none_like(value: str) -> bool:
    return value.strip().lower() in {"", "none", "n/a", "na"}


def _file_extension(url: str) -> str:
    path = urlparse(url).path.lower()
    if "." not in path:
        return ""
    return path.rsplit(".", maxsplit=1)[-1]


def _clean_sub_dataset_id(value: str) -> str:
    normalized = value.strip().lower() if value else ""
    if normalized in {"", "none", "n/a", "na"}:
        return "default"
    return normalized


def _normalize_object_name_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_")
    token = re.sub(r"_+", "_", token)
    return token.upper() or "DEFAULT"


def _infer_object_name_suffix(dataset_id: str, sub_dataset_id: str) -> str:
    return (
        f"{_normalize_object_name_token(dataset_id)}"
        f"_{_normalize_object_name_token(sub_dataset_id)}"
    )


def _infer_adls_path_prefix(dataset_id: str, sub_dataset_id: str) -> str:
    return f"{dataset_id}/{sub_dataset_id}"


def _read_inventory(path: Path) -> List[InventoryRow]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Inventory file has no header row.")

        dataset_col = _pick_header(reader.fieldnames, "name", "dataset name", "dataset")
        parent_col = _pick_header(reader.fieldnames, "parent link", "parent_link")
        sub_col = _pick_header(reader.fieldnames, "sub-link", "sub_link")
        collection_col = _pick_header(
            reader.fieldnames,
            "sub-collection",
            "sub_collection",
            "sub dataset",
            "sub_dataset",
        )
        target_col = _pick_header(
            reader.fieldnames,
            "target file",
            "target_file",
            "target file url",
            "target_url",
        )
        note_col = _pick_header(reader.fieldnames, "note", "notes")

        required = {
            "name": dataset_col,
            "parent link": parent_col,
            "sub-collection": collection_col,
            "target file": target_col,
        }
        missing = [label for label, col in required.items() if not col]
        if missing:
            raise ValueError(
                f"Missing required inventory columns: {', '.join(missing)}"
            )

        rows: List[InventoryRow] = []
        for raw in reader:
            rows.append(
                InventoryRow(
                    dataset_name=(raw.get(dataset_col, "") or "").strip(),
                    parent_link=(raw.get(parent_col, "") or "").strip(),
                    sub_link=(raw.get(sub_col, "") or "").strip() if sub_col else "",
                    sub_collection=(raw.get(collection_col, "") or "").strip(),
                    target_file=(raw.get(target_col, "") or "").strip(),
                    note=(raw.get(note_col, "") or "").strip() if note_col else "",
                )
            )
    return rows


def _rows_to_v2_payloads(
    rows: Sequence[InventoryRow], source_path: str
) -> Dict[str, Dict[str, object]]:
    by_dataset: Dict[str, List[InventoryRow]] = defaultdict(list)
    for row in rows:
        if row.dataset_name:
            by_dataset[row.dataset_name].append(row)

    payloads: Dict[str, Dict[str, object]] = {}
    for dataset_name, dataset_rows in sorted(
        by_dataset.items(), key=lambda item: item[0]
    ):
        entry_url = next(
            (
                row.parent_link
                for row in dataset_rows
                if not _is_none_like(row.parent_link)
            ),
            "",
        )
        if not entry_url:
            continue

        grouped_targets: Dict[str, List[InventoryRow]] = defaultdict(list)
        for row in dataset_rows:
            grouped_targets[_clean_sub_dataset_id(row.sub_collection)].append(row)

        targets: List[Dict[str, object]] = []
        for sub_dataset_id, target_rows in sorted(grouped_targets.items()):
            sample_subpage_url = next(
                (
                    row.sub_link
                    for row in target_rows
                    if not _is_none_like(row.sub_link)
                ),
                "",
            )

            samples: List[Sample] = []
            seen_urls: set[str] = set()
            for row in target_rows:
                if _is_none_like(row.target_file):
                    continue
                if row.target_file in seen_urls:
                    continue
                seen_urls.add(row.target_file)
                samples.append(Sample(file_url=row.target_file, notes=row.note.strip()))

            if not samples:
                continue

            include_extensions = sorted(
                {
                    _file_extension(sample.file_url)
                    for sample in samples
                    if _file_extension(sample.file_url)
                }
            )

            targets.append(
                {
                    "sub_dataset_id": sub_dataset_id,
                    "object_name_suffix": _infer_object_name_suffix(
                        _slugify(dataset_name), sub_dataset_id
                    ),
                    "adls_path_prefix": _infer_adls_path_prefix(
                        _slugify(dataset_name), sub_dataset_id
                    ),
                    "sample_subpage_url": sample_subpage_url,
                    "samples": [
                        {"file_url": sample.file_url, "notes": sample.notes}
                        for sample in samples
                    ],
                    "include_extensions": include_extensions,
                    "preferred_link_selector": "",
                    "preferred_text_filter": "",
                    "hints": {
                        "file_pattern": "",
                        "subject_period_pattern": "",
                        "fiscal_year_format": "",
                        "month_extraction": "",
                    },
                }
            )

        dataset_id = _slugify(dataset_name)
        payloads[dataset_id] = {
            "schema_version": "2.0",
            "dataset_id": dataset_id,
            "dataset_name": dataset_name,
            "entry_url": entry_url,
            "source_path": source_path,
            "hints": {
                "entry_structure": "",
                "publication_date": "",
                "subject_period": "",
            },
            "targets": targets,
        }

    return payloads


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate v2 helper input JSON files from an inventory CSV."
    )
    parser.add_argument(
        "--inventory",
        default="psds-file-inventory.csv",
        help="Path to inventory CSV file.",
    )
    parser.add_argument(
        "--output-dir",
        default="tools/scrape_config_builder/helper_input",
        help="Directory where v2 helper input JSON files will be written.",
    )
    parser.add_argument(
        "--dataset",
        action="append",
        default=[],
        help=(
            "Dataset ID or dataset name to write. Repeat for multiple datasets. "
            "If omitted, all datasets from the CSV are written."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    inventory_path = Path(args.inventory)
    if not inventory_path.exists():
        raise FileNotFoundError(f"Inventory file not found: {inventory_path}")

    rows = _read_inventory(inventory_path)
    payloads = _rows_to_v2_payloads(rows, str(inventory_path))

    indexed: Dict[str, Dict[str, object]] = {}
    for dataset_id, payload in payloads.items():
        indexed[dataset_id] = payload
        indexed[str(payload.get("dataset_name", ""))] = payload

    if args.dataset:
        selected_payloads: List[Dict[str, object]] = []
        seen: set[str] = set()
        for selector in args.dataset:
            payload = indexed.get(selector)
            if not payload:
                continue
            dataset_id = str(payload["dataset_id"])
            if dataset_id in seen:
                continue
            selected_payloads.append(payload)
            seen.add(dataset_id)
    else:
        selected_payloads = [payloads[k] for k in sorted(payloads.keys())]

    if not selected_payloads:
        raise ValueError("No matching datasets selected")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written_paths: List[Path] = []
    for payload in selected_payloads:
        output_path = output_dir / f"{payload['dataset_id']}.json"
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written_paths.append(output_path)

    print(f"Inventory: {inventory_path.resolve()}")
    print(f"Output directory: {output_dir.resolve()}")
    print(f"Files written: {len(written_paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
