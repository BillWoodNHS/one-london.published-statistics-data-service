"""Tests for tools/scrape_config_builder/validate-json-input.py.

Covers required-field rejection, enum validation for page_role and
partitioning_strategy, both schema versions, object_name_suffix and
adls_path_prefix rules, and datasets-array form.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_validator():
    path = REPO_ROOT / "tools" / "scrape_config_builder" / "validate-json-input.py"
    spec = importlib.util.spec_from_file_location("validator_module", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["validator_module"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def validator():
    return _load_validator()


def _write(tmp_path, payload):
    p = tmp_path / "input.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _minimal_target(**overrides):
    base = {
        "sub_dataset_id": "default",
        "sample_pages": [
            {
                "page_url": "https://example.com/page",
                "samples": [{"file_url": "https://example.com/file.csv"}],
            }
        ],
    }
    base.update(overrides)
    return base


def _minimal_v01(**overrides):
    base = {
        "schema_version": "0.1",
        "dataset_id": "demo-dataset",
        "entry_url": "https://example.com/dataset",
        "targets": [_minimal_target()],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


class TestValidatorAccepts:
    def test_minimal_valid_v01(self, validator, tmp_path):
        errors = validator.validate(_write(tmp_path, _minimal_v01()))
        assert errors == []

    def test_valid_v20_schema(self, validator, tmp_path):
        payload = {
            "schema_version": "2.0",
            "dataset_id": "demo",
            "entry_url": "https://example.com",
            "targets": [
                {
                    "sub_dataset_id": "default",
                    "sample_pages": [
                        {
                            "page_url": "https://example.com/page",
                            "samples": [{"file_url": "https://example.com/f.csv"}],
                        }
                    ],
                }
            ],
        }
        errors = validator.validate(_write(tmp_path, payload))
        assert errors == []

    def test_valid_datasets_array_form(self, validator, tmp_path):
        payload = {"datasets": [_minimal_v01(), _minimal_v01(dataset_id="other")]}
        errors = validator.validate(_write(tmp_path, payload))
        assert errors == []

    def test_accepts_valid_object_name_suffix(self, validator, tmp_path):
        payload = _minimal_v01(
            targets=[_minimal_target(object_name_suffix="AE_DEFAULT")]
        )
        errors = validator.validate(_write(tmp_path, payload))
        assert errors == []

    def test_accepts_valid_adls_path_prefix(self, validator, tmp_path):
        payload = _minimal_v01(targets=[_minimal_target(adls_path_prefix="ae/default")])
        errors = validator.validate(_write(tmp_path, payload))
        assert errors == []

    def test_no_object_name_suffix_required(self, validator, tmp_path):
        # suffix is optional — omitting should pass
        errors = validator.validate(_write(tmp_path, _minimal_v01()))
        assert errors == []


# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------


class TestValidatorRejectsRequiredFields:
    def test_missing_dataset_id(self, validator, tmp_path):
        payload = _minimal_v01()
        del payload["dataset_id"]
        errors = validator.validate(_write(tmp_path, payload))
        assert any("dataset_id" in e for e in errors)

    def test_missing_entry_url(self, validator, tmp_path):
        payload = _minimal_v01()
        del payload["entry_url"]
        errors = validator.validate(_write(tmp_path, payload))
        assert any("entry_url" in e for e in errors)

    def test_missing_sub_dataset_id(self, validator, tmp_path):
        target = _minimal_target()
        del target["sub_dataset_id"]
        payload = _minimal_v01(targets=[target])
        errors = validator.validate(_write(tmp_path, payload))
        assert any("sub_dataset_id" in e for e in errors)

    def test_empty_targets(self, validator, tmp_path):
        payload = _minimal_v01(targets=[])
        errors = validator.validate(_write(tmp_path, payload))
        assert errors  # targets must be non-empty

    def test_missing_sample_pages(self, validator, tmp_path):
        target = {"sub_dataset_id": "default", "sample_pages": []}
        payload = _minimal_v01(targets=[target])
        errors = validator.validate(_write(tmp_path, payload))
        assert errors

    def test_missing_file_url_in_sample(self, validator, tmp_path):
        target = {
            "sub_dataset_id": "default",
            "sample_pages": [
                {
                    "page_url": "https://example.com/page",
                    "samples": [{"notes": "no file url here"}],
                }
            ],
        }
        payload = _minimal_v01(targets=[target])
        errors = validator.validate(_write(tmp_path, payload))
        assert any("file_url" in e for e in errors)

    def test_missing_page_url(self, validator, tmp_path):
        target = {
            "sub_dataset_id": "default",
            "sample_pages": [
                {
                    "samples": [{"file_url": "https://example.com/f.csv"}],
                }
            ],
        }
        payload = _minimal_v01(targets=[target])
        errors = validator.validate(_write(tmp_path, payload))
        assert any("page_url" in e for e in errors)


# ---------------------------------------------------------------------------
# schema_version
# ---------------------------------------------------------------------------


class TestValidatorSchemaVersion:
    def test_bad_schema_version_rejected(self, validator, tmp_path):
        payload = _minimal_v01(schema_version="9.9")
        errors = validator.validate(_write(tmp_path, payload))
        assert any("schema_version" in e for e in errors)

    def test_missing_schema_version_rejected(self, validator, tmp_path):
        payload = _minimal_v01()
        del payload["schema_version"]
        errors = validator.validate(_write(tmp_path, payload))
        assert any("schema_version" in e for e in errors)


# ---------------------------------------------------------------------------
# page_role enum
# ---------------------------------------------------------------------------


class TestValidatorPageRole:
    @pytest.mark.parametrize(
        "role", ["default", "archive", "subject_period_index", "sub_dataset_dedicated"]
    )
    def test_valid_page_roles(self, validator, tmp_path, role):
        target = {
            "sub_dataset_id": "default",
            "sample_pages": [
                {
                    "page_url": "https://example.com/page",
                    "page_role": role,
                    "samples": [{"file_url": "https://example.com/f.csv"}],
                }
            ],
        }
        payload = _minimal_v01(targets=[target])
        errors = validator.validate(_write(tmp_path, payload))
        assert errors == []

    def test_invalid_page_role_rejected(self, validator, tmp_path):
        target = {
            "sub_dataset_id": "default",
            "sample_pages": [
                {
                    "page_url": "https://example.com/page",
                    "page_role": "not_a_real_role",
                    "samples": [{"file_url": "https://example.com/f.csv"}],
                }
            ],
        }
        payload = _minimal_v01(targets=[target])
        errors = validator.validate(_write(tmp_path, payload))
        assert any("page_role" in e for e in errors)


# ---------------------------------------------------------------------------
# partitioning_strategy enum
# ---------------------------------------------------------------------------


class TestValidatorPartitioningStrategy:
    @pytest.mark.parametrize("strategy", ["none", "subject_period", "mixed"])
    def test_valid_strategies(self, validator, tmp_path, strategy):
        target = {
            "sub_dataset_id": "default",
            "sample_pages": [
                {
                    "page_url": "https://example.com/page",
                    "partitioning_strategy": strategy,
                    "samples": [{"file_url": "https://example.com/f.csv"}],
                }
            ],
        }
        payload = _minimal_v01(targets=[target])
        errors = validator.validate(_write(tmp_path, payload))
        assert errors == []

    def test_invalid_strategy_rejected(self, validator, tmp_path):
        target = {
            "sub_dataset_id": "default",
            "sample_pages": [
                {
                    "page_url": "https://example.com/page",
                    "partitioning_strategy": "pagination",
                    "samples": [{"file_url": "https://example.com/f.csv"}],
                }
            ],
        }
        payload = _minimal_v01(targets=[target])
        errors = validator.validate(_write(tmp_path, payload))
        assert any("partitioning_strategy" in e for e in errors)


# ---------------------------------------------------------------------------
# object_name_suffix rules
# ---------------------------------------------------------------------------


class TestValidatorObjectNameSuffix:
    @pytest.mark.parametrize(
        "bad_suffix,reason",
        [
            ("lowercase_suffix", "lowercase"),
            ("RAW_DEMO_DEFAULT", "reserved prefix RAW_"),
            ("STG_DEMO", "reserved prefix STG_"),
            ("PIPE_DEMO", "reserved prefix PIPE_"),
            ("INGEST_DEMO", "reserved prefix INGEST_"),
            ("HAS SPACE", "contains space"),
            ("HAS-DASH", "contains dash"),
        ],
    )
    def test_invalid_suffixes_rejected(self, validator, tmp_path, bad_suffix, reason):
        payload = _minimal_v01(targets=[_minimal_target(object_name_suffix=bad_suffix)])
        errors = validator.validate(_write(tmp_path, payload))
        assert any("object_name_suffix" in e for e in errors), (
            f"Expected object_name_suffix error for {reason!r}, got: {errors}"
        )


# ---------------------------------------------------------------------------
# adls_path_prefix rules
# ---------------------------------------------------------------------------


class TestValidatorAdlsPathPrefix:
    def test_rejects_path_traversal(self, validator, tmp_path):
        payload = _minimal_v01(
            targets=[_minimal_target(adls_path_prefix="../sneaky/path")]
        )
        errors = validator.validate(_write(tmp_path, payload))
        assert any("adls_path_prefix" in e for e in errors)

    def test_rejects_absolute_path(self, validator, tmp_path):
        payload = _minimal_v01(
            targets=[_minimal_target(adls_path_prefix="/absolute/path")]
        )
        errors = validator.validate(_write(tmp_path, payload))
        assert any("adls_path_prefix" in e for e in errors)
