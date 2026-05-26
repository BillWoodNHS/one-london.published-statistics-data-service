from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class PromotionRecord:
    dataset_id: str
    source_yaml: Path
    destination_yaml: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Promote generated helper YAML configs into config/datasets. "
            "Source defaults to helper_generated/<dataset_id>/latest/"
            "generated_configs/."
        )
    )
    parser.add_argument(
        "--output-root",
        default="tools/scrape_config_builder/helper_generated",
        help="Root directory where helper-generated artifacts are stored.",
    )
    parser.add_argument(
        "--config-dir",
        default="config/datasets",
        help="Destination config directory.",
    )
    parser.add_argument(
        "--dataset",
        action="append",
        default=[],
        help=(
            "Dataset id to promote. Repeat for multiple datasets. "
            "If omitted, promote all dataset folders found in output root."
        ),
    )
    parser.add_argument(
        "--run-id",
        default="latest",
        help=(
            "Run folder to promote from. Defaults to latest. "
            "Examples: latest, run-20260526T120000Z"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview files that would be promoted without copying.",
    )
    return parser.parse_args()


def _discover_dataset_ids(output_root: Path) -> List[str]:
    if not output_root.exists():
        return []
    return sorted(path.name for path in output_root.iterdir() if path.is_dir())


def _collect_promotions(
    output_root: Path,
    config_dir: Path,
    dataset_ids: List[str],
    run_id: str,
) -> List[PromotionRecord]:
    records: List[PromotionRecord] = []
    missing: List[str] = []

    for dataset_id in dataset_ids:
        source_dir = output_root / dataset_id / run_id / "generated_configs"
        if not source_dir.exists():
            missing.append(f"{dataset_id} ({source_dir})")
            continue

        yaml_files = sorted(
            [
                *source_dir.glob("*.yaml"),
                *source_dir.glob("*.yml"),
            ]
        )
        if not yaml_files:
            missing.append(f"{dataset_id} ({source_dir} has no YAML files)")
            continue

        for yaml_file in yaml_files:
            records.append(
                PromotionRecord(
                    dataset_id=dataset_id,
                    source_yaml=yaml_file,
                    destination_yaml=config_dir / yaml_file.name,
                )
            )

    if missing:
        joined = "\n".join(f" - {item}" for item in missing)
        raise FileNotFoundError(
            "Some datasets are missing promotable generated YAML artifacts:\n" + joined
        )

    return records


def _apply_promotions(records: List[PromotionRecord], dry_run: bool) -> None:
    for record in records:
        if dry_run:
            continue
        record.destination_yaml.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(record.source_yaml, record.destination_yaml)


def main() -> int:
    args = parse_args()

    output_root = Path(args.output_root)
    config_dir = Path(args.config_dir)

    dataset_ids = (
        sorted(set(args.dataset))
        if args.dataset
        else _discover_dataset_ids(output_root)
    )
    if not dataset_ids:
        raise ValueError(
            f"No dataset ids selected or discovered under output root: {output_root}"
        )

    records = _collect_promotions(
        output_root=output_root,
        config_dir=config_dir,
        dataset_ids=dataset_ids,
        run_id=args.run_id,
    )
    _apply_promotions(records, dry_run=args.dry_run)

    print(f"Datasets selected: {len(dataset_ids)}")
    print(f"Run id: {args.run_id}")
    print(f"Promotion count: {len(records)}")
    for record in records:
        action = "WOULD COPY" if args.dry_run else "COPIED"
        print(
            f"{action}: {record.source_yaml.resolve()} -> "
            f"{record.destination_yaml.resolve()}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
