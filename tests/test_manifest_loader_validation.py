"""Tests for the error paths in function_app/src/manifest_loader.py.

Each test writes a minimal YAML to a temp directory and asserts that
load_manifests raises ManifestError with a relevant message, OR that it
accepts a valid manifest without error.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from function_app.src.manifest_loader import ManifestError, load_manifests

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_yaml(tmp_path: Path, data: dict, name: str = "test_manifest.yaml") -> Path:
    p = tmp_path / name
    p.write_text(yaml.dump(data), encoding="utf-8")
    return tmp_path


def _minimal_manifest(**overrides) -> dict:
    """Return a complete, valid manifest dict; apply overrides to top-level keys."""
    base = {
        "dataset_id": "test-dataset",
        "series_id": "test-series",
        "entry_url": "https://example.com",
        "publication_date": {"source": "link_text", "pattern": r"(\w+ \d{4})"},
        "fallback": {"allow_manual_acquisition": False},
        "targets": [
            {
                "sub_dataset_id": "default",
                "object_name_suffix": "TEST_DEFAULT",
                "adls_path_prefix": "test-dataset/default",
                "source_pages": [
                    {
                        "page_url": "https://example.com/page",
                        "scrape_steps": [{"link_selector": "a[href$='.csv']"}],
                    }
                ],
            }
        ],
    }
    base.update(overrides)
    return base


def _manifest_with_target_patch(tmp_path: Path, target_patch: dict) -> Path:
    manifest = _minimal_manifest()
    manifest["targets"][0].update(target_patch)
    return _write_yaml(tmp_path, manifest)


# ---------------------------------------------------------------------------
# Happy-path (no error)
# ---------------------------------------------------------------------------


class TestManifestLoaderHappyPath:
    def test_valid_minimal_manifest_loads(self, tmp_path):
        _write_yaml(tmp_path, _minimal_manifest())
        configs = load_manifests(tmp_path)
        assert len(configs) == 1
        assert configs[0].series_id == "test-series"

    def test_target_fields_populated(self, tmp_path):
        _write_yaml(tmp_path, _minimal_manifest())
        cfg = load_manifests(tmp_path)[0]
        target = cfg.targets[0]
        assert target.object_name_suffix == "TEST_DEFAULT"
        assert target.adls_path_prefix == "test-dataset/default"
        assert target.sub_dataset_id == "default"

    def test_empty_directory_returns_empty_list(self, tmp_path):
        configs = load_manifests(tmp_path)
        assert configs == []


# ---------------------------------------------------------------------------
# Required top-level fields
# ---------------------------------------------------------------------------


class TestManifestLoaderRequiredFields:
    def test_missing_dataset_id(self, tmp_path):
        data = _minimal_manifest()
        del data["dataset_id"]
        _write_yaml(tmp_path, data)
        with pytest.raises(ManifestError, match="dataset_id"):
            load_manifests(tmp_path)

    def test_missing_series_id(self, tmp_path):
        data = _minimal_manifest()
        del data["series_id"]
        _write_yaml(tmp_path, data)
        with pytest.raises(ManifestError, match="series_id"):
            load_manifests(tmp_path)

    def test_missing_entry_url(self, tmp_path):
        data = _minimal_manifest()
        del data["entry_url"]
        _write_yaml(tmp_path, data)
        with pytest.raises(ManifestError, match="entry_url"):
            load_manifests(tmp_path)

    def test_empty_targets_list(self, tmp_path):
        _write_yaml(tmp_path, _minimal_manifest(targets=[]))
        with pytest.raises(ManifestError, match="targets"):
            load_manifests(tmp_path)

    def test_missing_sub_dataset_id(self, tmp_path):
        _manifest_with_target_patch(tmp_path, {"sub_dataset_id": None})
        with pytest.raises(ManifestError, match="sub_dataset_id"):
            load_manifests(tmp_path)

    def test_scrape_steps_required_in_source_page(self, tmp_path):
        data = _minimal_manifest()
        data["targets"][0]["source_pages"][0]["scrape_steps"] = []
        _write_yaml(tmp_path, data)
        with pytest.raises(ManifestError, match="scrape_steps"):
            load_manifests(tmp_path)


# ---------------------------------------------------------------------------
# object_name_suffix validation
# ---------------------------------------------------------------------------


class TestManifestLoaderObjectNameSuffix:
    def test_missing_suffix_raises(self, tmp_path):
        data = _minimal_manifest()
        del data["targets"][0]["object_name_suffix"]
        _write_yaml(tmp_path, data)
        with pytest.raises(ManifestError, match="object_name_suffix"):
            load_manifests(tmp_path)

    def test_lowercase_suffix_raises(self, tmp_path):
        _manifest_with_target_patch(tmp_path, {"object_name_suffix": "lower_case"})
        with pytest.raises(ManifestError):
            load_manifests(tmp_path)

    def test_suffix_with_reserved_prefix_raw(self, tmp_path):
        _manifest_with_target_patch(tmp_path, {"object_name_suffix": "RAW_TEST"})
        with pytest.raises(ManifestError):
            load_manifests(tmp_path)

    def test_suffix_with_reserved_prefix_stg(self, tmp_path):
        _manifest_with_target_patch(tmp_path, {"object_name_suffix": "STG_TEST"})
        with pytest.raises(ManifestError):
            load_manifests(tmp_path)

    def test_suffix_with_reserved_prefix_pipe(self, tmp_path):
        _manifest_with_target_patch(tmp_path, {"object_name_suffix": "PIPE_TEST"})
        with pytest.raises(ManifestError):
            load_manifests(tmp_path)

    def test_suffix_with_reserved_prefix_ingest(self, tmp_path):
        _manifest_with_target_patch(tmp_path, {"object_name_suffix": "INGEST_TEST"})
        with pytest.raises(ManifestError):
            load_manifests(tmp_path)

    def test_suffix_with_space_raises(self, tmp_path):
        _manifest_with_target_patch(tmp_path, {"object_name_suffix": "HAS SPACE"})
        with pytest.raises(ManifestError):
            load_manifests(tmp_path)

    @pytest.mark.parametrize("valid", ["AE_DEFAULT", "A123", "MY_DATASET_DEFAULT"])
    def test_valid_suffixes_accepted(self, tmp_path, valid):
        _manifest_with_target_patch(tmp_path, {"object_name_suffix": valid})
        # No exception
        load_manifests(tmp_path)


# ---------------------------------------------------------------------------
# adls_path_prefix validation
# ---------------------------------------------------------------------------


class TestManifestLoaderAdlsPathPrefix:
    def test_missing_prefix_raises(self, tmp_path):
        data = _minimal_manifest()
        del data["targets"][0]["adls_path_prefix"]
        _write_yaml(tmp_path, data)
        with pytest.raises(ManifestError, match="adls_path_prefix"):
            load_manifests(tmp_path)

    def test_path_traversal_raises(self, tmp_path):
        _manifest_with_target_patch(tmp_path, {"adls_path_prefix": "../sneaky"})
        with pytest.raises(ManifestError, match="adls_path_prefix"):
            load_manifests(tmp_path)

    def test_absolute_path_raises(self, tmp_path):
        _manifest_with_target_patch(tmp_path, {"adls_path_prefix": "/absolute/path"})
        with pytest.raises(ManifestError, match="adls_path_prefix"):
            load_manifests(tmp_path)

    def test_uppercase_prefix_raises(self, tmp_path):
        _manifest_with_target_patch(tmp_path, {"adls_path_prefix": "UPPER/path"})
        with pytest.raises(ManifestError):
            load_manifests(tmp_path)

    @pytest.mark.parametrize(
        "valid",
        [
            "ae/default",
            "mental-health/performance-data",
            "single",
            "multi/segment/path",
        ],
    )
    def test_valid_prefixes_accepted(self, tmp_path, valid):
        _manifest_with_target_patch(tmp_path, {"adls_path_prefix": valid})
        cfg = load_manifests(tmp_path)
        assert cfg[0].targets[0].adls_path_prefix == valid
