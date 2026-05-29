from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module at {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_validate_json_input_accepts_optional_object_name_suffix(tmp_path):
    validator = _load_module(
        "validate_json_input",
        "tools/scrape_config_builder/validate-json-input.py",
    )
    payload = {
        "schema_version": "0.1",
        "dataset_id": "demo-dataset",
        "entry_url": "https://example.com/dataset",
        "targets": [
            {
                "sub_dataset_id": "default",
                "sample_pages": [
                    {
                        "page_url": "https://example.com/page",
                        "samples": [{"file_url": "https://example.com/file.csv"}],
                    }
                ],
            },
            {
                "sub_dataset_id": "custom",
                "object_name_suffix": "DEMO_CUSTOM",
                "sample_pages": [
                    {
                        "page_url": "https://example.com/page-2",
                        "samples": [{"file_url": "https://example.com/file-2.csv"}],
                    }
                ],
            },
        ],
    }
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert validator.validate(path) == []


def test_validate_json_input_rejects_prefixed_object_name_suffix(tmp_path):
    validator = _load_module(
        "validate_json_input_invalid",
        "tools/scrape_config_builder/validate-json-input.py",
    )
    payload = {
        "schema_version": "0.1",
        "dataset_id": "demo-dataset",
        "entry_url": "https://example.com/dataset",
        "targets": [
            {
                "sub_dataset_id": "default",
                "object_name_suffix": "RAW_DEMO_DEFAULT",
                "sample_pages": [
                    {
                        "page_url": "https://example.com/page",
                        "samples": [{"file_url": "https://example.com/file.csv"}],
                    }
                ],
            }
        ],
    }
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    errors = validator.validate(path)
    assert any("object_name_suffix" in error for error in errors)


def test_helper_infers_object_name_suffix_when_missing(tmp_path):
    helper = _load_module(
        "scrape_config_helper",
        "tools/scrape_config_builder/scrape-config-helper.py",
    )
    payload = {
        "schema_version": "0.1",
        "dataset_id": "demo-dataset",
        "dataset_name": "Demo Dataset",
        "entry_url": "https://example.com/dataset",
        "targets": [
            {
                "sub_dataset_id": "special-case",
                "sample_pages": [
                    {
                        "page_url": "https://example.com/page",
                        "page_role": "default",
                        "partitioning_strategy": "none",
                        "samples": [{"file_url": "https://example.com/file.csv"}],
                    }
                ],
            }
        ],
    }
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    specs = helper._read_json_dataset_specs(path)

    assert specs[0].targets[0].object_name_suffix == "DEMO_DATASET_SPECIAL_CASE"


def test_csv_generator_populates_default_object_name_suffix():
    generator = _load_module(
        "generate_helper_input_from_csv",
        "tools/scrape_config_builder/generate-helper-input-from-csv.py",
    )
    rows = [
        generator.InventoryRow(
            dataset_name="Appointments in General Practice",
            parent_link="https://example.com/dataset",
            sub_link="",
            sub_collection="practice-level",
            target_file="https://example.com/file.csv",
            note="",
        )
    ]

    payloads = generator._rows_to_v2_payloads(rows, "inventory.csv")

    target = payloads["appointments-in-general-practice"]["targets"][0]
    assert (
        target["object_name_suffix"]
        == "APPOINTMENTS_IN_GENERAL_PRACTICE_PRACTICE_LEVEL"
    )


def test_validate_json_input_accepts_valid_adls_path_prefix(tmp_path):
    validator = _load_module(
        "validate_json_input_adls",
        "tools/scrape_config_builder/validate-json-input.py",
    )
    payload = {
        "schema_version": "0.1",
        "dataset_id": "demo-dataset",
        "entry_url": "https://example.com/dataset",
        "targets": [
            {
                "sub_dataset_id": "default",
                "adls_path_prefix": "demo-dataset/default",
                "sample_pages": [
                    {
                        "page_url": "https://example.com/page",
                        "samples": [{"file_url": "https://example.com/file.csv"}],
                    }
                ],
            }
        ],
    }
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert validator.validate(path) == []


def test_validate_json_input_rejects_path_traversal_in_adls_path_prefix(tmp_path):
    validator = _load_module(
        "validate_json_input_adls_invalid",
        "tools/scrape_config_builder/validate-json-input.py",
    )
    payload = {
        "schema_version": "0.1",
        "dataset_id": "demo-dataset",
        "entry_url": "https://example.com/dataset",
        "targets": [
            {
                "sub_dataset_id": "default",
                "adls_path_prefix": "../other-container/evil",
                "sample_pages": [
                    {
                        "page_url": "https://example.com/page",
                        "samples": [{"file_url": "https://example.com/file.csv"}],
                    }
                ],
            }
        ],
    }
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    errors = validator.validate(path)
    assert any("adls_path_prefix" in error for error in errors)


def test_helper_infers_adls_path_prefix_when_missing(tmp_path):
    helper = _load_module(
        "scrape_config_helper_adls",
        "tools/scrape_config_builder/scrape-config-helper.py",
    )
    payload = {
        "schema_version": "0.1",
        "dataset_id": "demo-dataset",
        "dataset_name": "Demo Dataset",
        "entry_url": "https://example.com/dataset",
        "targets": [
            {
                "sub_dataset_id": "special-case",
                "sample_pages": [
                    {
                        "page_url": "https://example.com/page",
                        "page_role": "default",
                        "partitioning_strategy": "none",
                        "samples": [{"file_url": "https://example.com/file.csv"}],
                    }
                ],
            }
        ],
    }
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    specs = helper._read_json_dataset_specs(path)

    assert specs[0].targets[0].adls_path_prefix == "demo-dataset/special-case"


def test_csv_generator_populates_default_adls_path_prefix():
    generator = _load_module(
        "generate_helper_input_from_csv_adls",
        "tools/scrape_config_builder/generate-helper-input-from-csv.py",
    )
    rows = [
        generator.InventoryRow(
            dataset_name="Appointments in General Practice",
            parent_link="https://example.com/dataset",
            sub_link="",
            sub_collection="practice-level",
            target_file="https://example.com/file.csv",
            note="",
        )
    ]

    payloads = generator._rows_to_v2_payloads(rows, "inventory.csv")

    target = payloads["appointments-in-general-practice"]["targets"][0]
    assert (
        target["adls_path_prefix"] == "appointments-in-general-practice/practice-level"
    )
