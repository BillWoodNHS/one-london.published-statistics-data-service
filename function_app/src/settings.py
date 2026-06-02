from __future__ import annotations

# Minimum plausible publication date for NHS statistics scraped by this service.
# Any date extracted from a source page that predates this threshold is treated as
# a scraper misfire and is replaced with the download timestamp (ingest-fallback).
# Format: YYYYMMDDTHHMMSS (compact ISO, matching normalize_datetime_value output).
MIN_PLAUSIBLE_PUBLICATION_DATE: str = "20100101T000000"
