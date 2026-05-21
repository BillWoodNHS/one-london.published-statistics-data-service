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

    artifact = build_artifact(discovered, "data.csv", "abc123")
    expected_prefix = (
        "mental-health-services-monthly-statistics/restrictive-interventions/"
        "publication_date=20260519T103600/"
    )
    assert artifact.adls_path.startswith(expected_prefix)
