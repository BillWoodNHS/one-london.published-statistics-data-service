from pathlib import Path

from function_app.src.manifest_loader import load_manifests


def test_manifest_loads_targets():
    root = Path(__file__).resolve().parents[1] / "config" / "datasets"
    manifests = load_manifests(root)

    assert manifests
    mh = next(
        m
        for m in manifests
        if m.series_id == "mental-health-services-monthly-statistics"
    )
    assert len(mh.targets) == 3
    # Find performance-data-file target instead of relying on order
    perf_target = next(
        t for t in mh.targets if t.sub_dataset_id == "performance-data-file"
    )
    assert perf_target.sub_dataset_id == "performance-data-file"
    assert perf_target.object_name_suffix
    assert perf_target.adls_path_prefix
    assert mh.subject_period is not None
    assert perf_target.page_date_selectors
    assert perf_target.source_pages
    assert perf_target.source_pages[0].page_role == "default"
    assert perf_target.period_coverage is not None
    assert perf_target.period_coverage.file_scope.duration_type == "unknown"
    assert perf_target.period_coverage.file_scope.fiscal_year_start_month == 4
    assert perf_target.period_coverage.breakdown_granularity == ["month"]
