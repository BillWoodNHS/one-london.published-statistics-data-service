from __future__ import annotations

from pathlib import Path

from tools.local_dev.schema_drift import (
    KnownSchema,
    _jaccard_distance,
    detect_drift,
    load_known_schema,
    warnings_to_json,
)


def test_jaccard_distance_identical_sets_is_zero():
    distance = _jaccard_distance({"a", "b"}, {"a", "b"})

    assert distance == 0.0


def test_jaccard_distance_disjoint_sets_is_one():
    distance = _jaccard_distance({"a", "b"}, {"c", "d"})

    assert distance == 1.0


def test_jaccard_distance_partial_overlap():
    distance = _jaccard_distance({"a", "b", "c"}, {"a", "b", "d"})

    assert distance == 0.5


def test_load_known_schema_returns_columns_when_present(tmp_path: Path):
    schema_root = tmp_path / "schemas"
    schema_root.mkdir()
    (schema_root / "my-dataset.yaml").write_text(
        "schemas:\n  MY_SUFFIX:\n    columns: [ColA, ColB]\n",
        encoding="utf-8",
    )

    known = load_known_schema(schema_root, "my-dataset", "MY_SUFFIX")

    assert known == KnownSchema(
        object_name_suffix="MY_SUFFIX", columns=["ColA", "ColB"]
    )


def test_load_known_schema_returns_none_when_dataset_file_missing(tmp_path: Path):
    known = load_known_schema(tmp_path / "schemas", "missing-dataset", "MY_SUFFIX")

    assert known is None


def test_load_known_schema_returns_none_when_suffix_missing(tmp_path: Path):
    schema_root = tmp_path / "schemas"
    schema_root.mkdir()
    (schema_root / "my-dataset.yaml").write_text(
        "schemas:\n  OTHER_SUFFIX:\n    columns: [ColA]\n",
        encoding="utf-8",
    )

    known = load_known_schema(schema_root, "my-dataset", "MY_SUFFIX")

    assert known is None


def test_detect_drift_returns_none_under_threshold():
    known = KnownSchema(
        object_name_suffix="MY_SUFFIX", columns=["ColA", "ColB", "ColC"]
    )

    warning = detect_drift(known, ["ColA", "ColB", "ColC"], threshold=0.20)

    assert warning is None


def test_detect_drift_returns_warning_over_threshold():
    known = KnownSchema(
        object_name_suffix="MY_SUFFIX", columns=["ColA", "ColB", "ColC"]
    )

    warning = detect_drift(known, ["ColA", "ColX"], threshold=0.20)

    assert warning is not None
    assert warning.table_name == "MY_SUFFIX"
    assert warning.drift_ratio == 0.75


def test_warnings_to_json_serializes_path_to_string():
    known = KnownSchema(
        object_name_suffix="MY_SUFFIX", columns=["ColA", "ColB", "ColC"]
    )
    warning = detect_drift(known, ["ColA", "ColX"], threshold=0.20)
    warning.csv_path = Path("some") / "file.csv"

    payload = warnings_to_json([warning])

    assert payload == [
        {
            "table_name": "MY_SUFFIX",
            "csv_path": str(Path("some") / "file.csv"),
            "known_columns": ["ColA", "ColB", "ColC"],
            "actual_columns": ["ColA", "ColX"],
            "drift_ratio": 0.75,
        }
    ]
