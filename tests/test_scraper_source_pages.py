from __future__ import annotations

from function_app.src.models import (
    DatasetSeriesConfig,
    PublicationDateRule,
    ScrapeStep,
    SiblingDiscoveryConfig,
    SourcePageConfig,
    TargetConfig,
)
from function_app.src.scraper import discover_files


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_source_pages_sibling_discovery_finds_new_financial_year_pages(monkeypatch):
    html_by_url = {
        "https://example.com/dqmi": """
            <html><body>
                <a href=\"/dqmi/fy-2024-25\">FY 2024-25</a>
                <a href=\"/dqmi/fy-2025-26\">FY 2025-26</a>
                <a href=\"/files/current_did.csv\">Current DID CSV</a>
            </body></html>
        """,
        "https://example.com/dqmi/fy-2024-25": """
            <html><body>
                <a href=\"/files/fy-2024-25_did.csv\">FY 2024-25 DID CSV</a>
            </body></html>
        """,
        "https://example.com/dqmi/fy-2025-26": """
            <html><body>
                <a href=\"/files/fy-2025-26_did.csv\">FY 2025-26 DID CSV</a>
                <a href=\"/files/current_did.csv\">Current DID CSV</a>
            </body></html>
        """,
    }

    def fake_get(self, url, timeout=60):
        if url not in html_by_url:
            return _FakeResponse("", status_code=404)
        return _FakeResponse(html_by_url[url])

    monkeypatch.setattr("requests.sessions.Session.get", fake_get)

    config = DatasetSeriesConfig(
        dataset_id="dqmi",
        series_id="dqmi",
        entry_url="https://example.com/dqmi",
        publication_date=PublicationDateRule(
            source="link_text", pattern=r"(March 2026)"
        ),
        targets=[
            TargetConfig(
                sub_dataset_id="with-did",
                source_pages=[
                    SourcePageConfig(
                        page_url="https://example.com/dqmi",
                        page_role="sub_dataset_dedicated",
                        partitioning_strategy="subject_period",
                        scrape_steps=[
                            ScrapeStep(
                                link_selector="a[href$='.csv']",
                                file_extensions=["csv"],
                            )
                        ],
                        sibling_discovery=SiblingDiscoveryConfig(
                            enabled=True,
                            link_selector="a[href]",
                            max_pages=10,
                        ),
                    )
                ],
            )
        ],
    )

    discovered = discover_files(config)
    urls = sorted(item.source_url for item in discovered)

    assert "https://example.com/files/current_did.csv" in urls
    assert "https://example.com/files/fy-2024-25_did.csv" in urls
    assert "https://example.com/files/fy-2025-26_did.csv" in urls

    # Deduplication should keep one copy when the same file appears on multiple pages.
    assert urls.count("https://example.com/files/current_did.csv") == 1
