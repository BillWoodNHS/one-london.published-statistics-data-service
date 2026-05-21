from pathlib import Path

from function_app.src.manifest_loader import load_manifests


def test_manifest_loads_targets():
    root = Path(__file__).resolve().parents[1] / "config" / "datasets"
    manifests = load_manifests(root)

    assert manifests
    mh = next(m for m in manifests if m.series_id == "mental-health-services-monthly-statistics")
    assert len(mh.targets) == 3
    assert mh.targets[0].sub_dataset_id == "performance-data-file"
