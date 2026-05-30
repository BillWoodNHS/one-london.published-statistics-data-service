"""Integration tests: live web scraping baseline.

These tests perform real HTTP requests and are skipped unless the
``--run-integration`` flag is passed or the INTEGRATION_TESTS env var is set.

Each test records a known-minimum set of file URLs that must be present
after scraping; new files can be added but no known URL may disappear.

Run with:
    pytest -m integration
or:
    INTEGRATION_TESTS=1 python -m pytest tests/test_live_scraper_baseline.py -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from function_app.src.manifest_loader import load_manifests
from function_app.src.scraper import discover_files

INTEGRATION_TESTS = bool(os.environ.get("INTEGRATION_TESTS"))

pytestmark = pytest.mark.skipif(
    not INTEGRATION_TESTS,
    reason="Set INTEGRATION_TESTS=1 to run live scraper tests",
)

MANIFEST_ROOT = Path(__file__).resolve().parents[1] / "config" / "datasets"


def _discover_urls_for_series(series_id: str) -> set[str]:
    """Return the set of discovered file URLs for a given series."""
    manifests = load_manifests(MANIFEST_ROOT)
    config = next(m for m in manifests if m.series_id == series_id)
    files = discover_files(config)
    return {f.source_url for f in files}


# ---------------------------------------------------------------------------
# A&E (Accident & Emergency)
# ---------------------------------------------------------------------------

AE_SERIES = "accident-and-emergency-attendances-and-emergency-admissions"

# At least these URLs must be discoverable.  Update when NHS England restructures.
AE_KNOWN_URLS: set[str] = set()  # populated lazily by the baseline run


@pytest.mark.integration
def test_ae_discovers_csv_files():
    """A&E scraper discovers at least one CSV file."""
    urls = _discover_urls_for_series(AE_SERIES)
    csv_urls = {u for u in urls if u.lower().endswith(".csv")}
    assert csv_urls, f"Expected at least one CSV URL, found: {urls}"


@pytest.mark.integration
def test_ae_discovered_files_are_valid_urls():
    """All discovered A&E URLs look like valid HTTP(S) URLs."""
    urls = _discover_urls_for_series(AE_SERIES)
    assert urls, "Expected at least some discovered files"
    for url in urls:
        assert url.startswith("https://") or url.startswith("http://"), (
            f"Non-HTTP URL discovered: {url}"
        )


# ---------------------------------------------------------------------------
# DQMI (Data Quality Maturity Index) — typically more stable / fewer files
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_dqmi_discovers_at_least_one_file():
    """DQMI scraper discovers at least one downloadable file."""
    manifests = load_manifests(MANIFEST_ROOT)
    dqmi_manifests = [
        m for m in manifests if "data-quality" in m.series_id or "dqmi" in m.series_id
    ]
    if not dqmi_manifests:
        pytest.skip("No DQMI manifest found")

    config = dqmi_manifests[0]
    files = discover_files(config)
    assert files, f"Expected at least one file from {config.series_id}"


# ---------------------------------------------------------------------------
# Generic: all manifests produce at least one file
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize(
    "series_id",
    [m.series_id for m in load_manifests(MANIFEST_ROOT)] if INTEGRATION_TESTS else [],
    ids=lambda s: s,
)
def test_each_manifest_discovers_at_least_one_file(series_id):
    """Every configured manifest must discover at least one file from the live web."""
    urls = _discover_urls_for_series(series_id)
    assert urls, f"{series_id}: no files discovered — scraper config may be broken"
