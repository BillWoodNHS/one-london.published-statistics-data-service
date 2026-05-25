from pathlib import Path

from function_app.src.manifest_loader import load_manifests


def test_manifest_loads_targets():
    root = Path(__file__).resolve().parents[1] / "config" / "datasets"
    manifests = load_manifests(root)

    assert manifests
    mh = next(
        m
        for m in manifests
        if m.series_id == "mental_health_services_monthly_statistics"
    )
    assert len(mh.targets) == 3
    # Find performance-data-file target instead of relying on order
    perf_target = next(
        t for t in mh.targets if t.sub_dataset_id == "performance-data-file"
    )
    assert perf_target.sub_dataset_id == "performance-data-file"
    assert mh.subject_period is not None
    assert perf_target.page_date_selectors
    assert perf_target.source_pages
    assert perf_target.source_pages[0].page_role == "default"
