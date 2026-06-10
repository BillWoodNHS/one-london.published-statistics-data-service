from function_app.src.download_and_normalize import build_artifact
from function_app.src.models import DiscoveredFile


def test_sub_dataset_isolation_path():
    discovered = DiscoveredFile(
        dataset_id="mh",
        series_id="mental-health-services-monthly-statistics",
        sub_dataset_id="restrictive-interventions",
        source_url="https://example.com/data.csv",
        publication_date_value="20260519T103600",
        link_text="March 2026",
    )

    artifact = build_artifact(discovered, "data.csv", "abc123", "20260519T103600")
    expected_prefix = (
        "mental-health-services-monthly-statistics/restrictive-interventions/"
        "download_year=2026/"
        "download_month=05/"
        "downloaded_at=20260519T103600/"
    )
    assert artifact.adls_path.startswith(expected_prefix)


def test_explicit_adls_path_prefix_overrides_default():
    discovered = DiscoveredFile(
        dataset_id="mh",
        series_id="mental-health-services-monthly-statistics",
        sub_dataset_id="restrictive-interventions",
        source_url="https://example.com/data.csv",
        publication_date_value="20260519T103600",
        link_text="March 2026",
        adls_path_prefix="mental_health_services_monthly_statistics/restrictive-interventions",
    )

    artifact = build_artifact(discovered, "data.csv", "abc123", "20260519T103600")
    expected_prefix = (
        "mental_health_services_monthly_statistics/restrictive-interventions/"
        "download_year=2026/"
        "download_month=05/"
        "downloaded_at=20260519T103600/"
    )
    assert artifact.adls_path.startswith(expected_prefix)
