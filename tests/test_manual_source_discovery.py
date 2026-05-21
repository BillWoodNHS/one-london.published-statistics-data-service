from function_app.src.manual_sources import discover_manual_files
from function_app.src.models import (
    DatasetSeriesConfig,
    FallbackConfig,
    PublicationDateRule,
    ScrapeStep,
    TargetConfig,
)


def test_manual_source_discovery_uses_adls_prefix(monkeypatch):
    def fake_list_blob_paths(prefix):
        expected_prefix = (
            "manual/mental-health-services-monthly-statistics/"
            "restrictive-interventions/"
        )
        assert prefix == expected_prefix
        return [
            "manual/mental-health-services-monthly-statistics/"
            "restrictive-interventions/restrictive_20260519T103600.csv",
            "manual/mental-health-services-monthly-statistics/"
            "restrictive-interventions/readme.txt",
        ]

    monkeypatch.setattr(
        "function_app.src.manual_sources.list_blob_paths", fake_list_blob_paths
    )

    config = DatasetSeriesConfig(
        dataset_id="mh",
        series_id="mental-health-services-monthly-statistics",
        entry_url="https://example.com",
        publication_date=PublicationDateRule(
            source="url_segment", pattern="(\\d{8}T\\d{6})"
        ),
        targets=[
            TargetConfig(
                sub_dataset_id="restrictive-interventions",
                scrape_steps=[ScrapeStep(link_selector="a[href]")],
            )
        ],
        fallback=FallbackConfig(),
    )

    discovered = discover_manual_files(config, config.targets[0], "manual")
    assert len(discovered) == 1
    assert discovered[0].publication_date_value == "20260519T103600"
