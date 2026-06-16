"""Tests for normalize_payload_to_csv, _all_csvs_from_zip, _excel_to_csv,
_count_csv_rows, and build_artifact in function_app/src/download_and_normalize.py.
"""

from __future__ import annotations

import io
import zipfile

import openpyxl
import pandas as pd
import pytest

from function_app.src.download_and_normalize import (
    _all_csvs_from_zip,
    _count_csv_rows,
    _excel_to_csv,
    _ods_to_csv,
    normalize_payload_to_csv,
)

# ---------------------------------------------------------------------------
# Helpers to build test payloads in memory
# ---------------------------------------------------------------------------


def _make_zip(*members: tuple[str, bytes]) -> bytes:
    """Build an in-memory ZIP containing (name, data) members."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members:
            zf.writestr(name, data)
    return buf.getvalue()


def _make_xlsx(headers: list[str], rows: list[list]) -> bytes:
    """Build an in-memory .xlsx workbook."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_ods(headers: list[str], rows: list[list]) -> bytes:
    """Build an in-memory .ods workbook."""
    frame = pd.DataFrame(rows, columns=headers)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="odf") as writer:
        frame.to_excel(writer, index=False)
    return buf.getvalue()


CSV_SIMPLE = b"col_a,col_b\n1,2\n3,4\n5,6\n"
CSV_HEADER_ONLY = b"col_a,col_b\n"
CSV_EMPTY = b""


# ---------------------------------------------------------------------------
# _count_csv_rows
# ---------------------------------------------------------------------------


class TestCountCsvRows:
    def test_counts_data_rows_excluding_header(self):
        assert _count_csv_rows(CSV_SIMPLE) == 3

    def test_header_only_returns_zero(self):
        assert _count_csv_rows(CSV_HEADER_ONLY) == 0

    def test_empty_payload_returns_zero(self):
        assert _count_csv_rows(CSV_EMPTY) == 0

    def test_bom_encoded_utf8(self):
        bom_csv = b"\xef\xbb\xbfcol_a,col_b\n1,2\n"
        assert _count_csv_rows(bom_csv) == 1

    def test_latin1_encoded(self):
        latin1_csv = "col\n\xe9l\xe8ve\n".encode("latin-1")
        assert _count_csv_rows(latin1_csv) == 1


# ---------------------------------------------------------------------------
# _all_csvs_from_zip
# ---------------------------------------------------------------------------


class TestAllCsvsFromZip:
    def test_extracts_csv_from_zip(self):
        payload = _make_zip(("data.csv", CSV_SIMPLE))
        ((name, content, metrics),) = _all_csvs_from_zip(payload)
        assert name == "data.csv"
        assert content == CSV_SIMPLE
        assert metrics["source_file_type"] == "zip"
        assert metrics["extracted_from_archive"] is True
        assert metrics["converted_to_csv"] is False
        assert metrics["raw_row_count"] == 3

    def test_extracts_all_files_from_zip(self):
        xlsx_payload = _make_xlsx(["a", "b"], [[1, 2]])
        payload = _make_zip(
            ("spreadsheet.xlsx", xlsx_payload),
            ("data.csv", CSV_SIMPLE),
        )
        results = _all_csvs_from_zip(payload)
        names = {name for name, _, _ in results}
        assert names == {"spreadsheet.csv", "data.csv"}

        by_name = {name: metrics for name, _, metrics in results}
        assert by_name["spreadsheet.csv"]["converted_to_csv"] is True
        assert by_name["data.csv"]["converted_to_csv"] is False

    def test_converts_xlsx_when_no_csv_in_zip(self):
        xlsx_payload = _make_xlsx(["x", "y"], [[10, 20], [30, 40]])
        payload = _make_zip(("report.xlsx", xlsx_payload))
        ((name, content, metrics),) = _all_csvs_from_zip(payload)
        assert name == "report.csv"
        assert metrics["converted_to_csv"] is True
        assert metrics["source_file_type"] == "zip"
        assert metrics["extracted_from_archive"] is True
        assert metrics["raw_row_count"] == 2

    def test_raises_when_zip_contains_no_usable_file(self):
        payload = _make_zip(("readme.txt", b"some text"))
        with pytest.raises(ValueError, match="ZIP did not contain"):
            _all_csvs_from_zip(payload)

    def test_converts_ods_when_no_csv_or_excel_in_zip(self):
        ods_payload = _make_ods(["x", "y"], [[10, 20], [30, 40]])
        payload = _make_zip(("report.ods", ods_payload))
        ((name, content, metrics),) = _all_csvs_from_zip(payload)
        assert name == "report.csv"
        assert metrics["converted_to_csv"] is True
        assert metrics["source_file_type"] == "zip"
        assert metrics["extracted_from_archive"] is True
        assert metrics["raw_row_count"] == 2


# ---------------------------------------------------------------------------
# _excel_to_csv
# ---------------------------------------------------------------------------


class TestExcelToCsv:
    def test_converts_xlsx_to_csv(self):
        xlsx = _make_xlsx(["name", "score"], [["alice", 95], ["bob", 87]])
        name, content, metrics = _excel_to_csv("my_report", xlsx, ".xlsx")
        assert name == "my_report.csv"
        decoded = content.decode("utf-8")
        assert "name,score" in decoded
        assert "alice" in decoded
        assert metrics["converted_to_csv"] is True
        assert metrics["source_file_type"] == "excel"
        assert metrics["raw_row_count"] == 2
        assert metrics["normalized_row_count"] == 2
        assert metrics["extracted_from_archive"] is False

    def test_converted_csv_has_correct_row_count(self):
        xlsx = _make_xlsx(["a"], [[1], [2], [3], [4], [5]])
        _, content, metrics = _excel_to_csv("data", xlsx, ".xlsx")
        assert metrics["raw_row_count"] == 5
        assert _count_csv_rows(content) == 5


class TestOdsToCsv:
    def test_converts_ods_to_csv(self):
        ods = _make_ods(["name", "score"], [["alice", 95], ["bob", 87]])
        name, content, metrics = _ods_to_csv("my_report", ods, ".ods")
        assert name == "my_report.csv"
        decoded = content.decode("utf-8")
        assert "name,score" in decoded
        assert "alice" in decoded
        assert metrics["converted_to_csv"] is True
        assert metrics["source_file_type"] == "ods"
        assert metrics["raw_row_count"] == 2
        assert metrics["normalized_row_count"] == 2
        assert metrics["extracted_from_archive"] is False

    def test_converted_ods_has_correct_row_count(self):
        ods = _make_ods(["a"], [[1], [2], [3], [4], [5]])
        _, content, metrics = _ods_to_csv("data", ods, ".ods")
        assert metrics["raw_row_count"] == 5
        assert _count_csv_rows(content) == 5

    def test_empty_ods_returns_zero_rows(self):
        ods = _make_ods(["header"], [])
        _, content, metrics = _ods_to_csv("empty", ods, ".ods")
        assert metrics["raw_row_count"] == 0
        assert _count_csv_rows(content) == 0


# ---------------------------------------------------------------------------
# normalize_payload_to_csv
# ---------------------------------------------------------------------------


class TestNormalizePayloadToCsv:
    def test_csv_passthrough(self):
        ((name, content, h, metrics),) = normalize_payload_to_csv(
            "data.csv", CSV_SIMPLE
        )
        assert name == "data.csv"
        assert content == CSV_SIMPLE
        assert metrics["source_file_type"] == "csv"
        assert metrics["converted_to_csv"] is False
        assert metrics["extracted_from_archive"] is False
        assert len(h) == 64  # SHA-256 hex

    def test_zip_containing_csv(self):
        zip_payload = _make_zip(("result.csv", CSV_SIMPLE))
        ((name, content, h, metrics),) = normalize_payload_to_csv(
            "archive.zip", zip_payload
        )
        assert name == "result.csv"
        assert metrics["source_file_type"] == "zip"
        assert metrics["extracted_from_archive"] is True
        assert metrics["converted_to_csv"] is False

    def test_zip_containing_multiple_files(self):
        xlsx = _make_xlsx(["a", "b"], [[1, 2]])
        zip_payload = _make_zip(
            ("report.xlsx", xlsx),
            ("data.csv", CSV_SIMPLE),
        )
        results = normalize_payload_to_csv("archive.zip", zip_payload)
        names = {name for name, _, _, _ in results}
        assert names == {"report.csv", "data.csv"}

    def test_zip_containing_xlsx(self):
        xlsx = _make_xlsx(["a", "b"], [[1, 2]])
        zip_payload = _make_zip(("report.xlsx", xlsx))
        ((name, content, h, metrics),) = normalize_payload_to_csv(
            "archive.zip", zip_payload
        )
        assert name == "report.csv"
        assert metrics["converted_to_csv"] is True
        assert metrics["source_file_type"] == "zip"

    def test_bare_xlsx(self):
        xlsx = _make_xlsx(["col"], [["val1"], ["val2"]])
        ((name, content, h, metrics),) = normalize_payload_to_csv("report.xlsx", xlsx)
        assert name == "report.csv"
        assert metrics["source_file_type"] == "excel"
        assert metrics["converted_to_csv"] is True
        assert metrics["raw_row_count"] == 2

    def test_bare_xls_extension_handled(self):
        # Build a valid xlsx and lie about the extension
        xlsx = _make_xlsx(["x"], [[1]])
        ((name, content, h, metrics),) = normalize_payload_to_csv("old.xls", xlsx)
        assert name == "old.csv"

    def test_bare_ods(self):
        ods = _make_ods(["col"], [["val1"], ["val2"]])
        ((name, content, h, metrics),) = normalize_payload_to_csv("report.ods", ods)
        assert name == "report.csv"
        assert metrics["source_file_type"] == "ods"
        assert metrics["converted_to_csv"] is True
        assert metrics["raw_row_count"] == 2

    def test_zip_containing_ods(self):
        ods = _make_ods(["a", "b"], [[1, 2]])
        zip_payload = _make_zip(("report.ods", ods))
        ((name, content, h, metrics),) = normalize_payload_to_csv(
            "archive.zip", zip_payload
        )
        assert name == "report.csv"
        assert metrics["converted_to_csv"] is True
        assert metrics["source_file_type"] == "zip"

    def test_unsupported_extension_raises(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            normalize_payload_to_csv("report.pdf", b"%PDF-1.4")

    def test_zip_member_content_hash_is_of_extracted_content(self):
        import hashlib

        zip_payload = _make_zip(("x.csv", CSV_SIMPLE))
        ((_, content, h, _),) = normalize_payload_to_csv("archive.zip", zip_payload)
        assert h == hashlib.sha256(content).hexdigest()

    def test_source_and_normalized_bytes_in_metrics(self):
        zip_payload = _make_zip(("x.csv", CSV_SIMPLE))
        ((_, content, _, metrics),) = normalize_payload_to_csv(
            "archive.zip", zip_payload
        )
        assert metrics["source_bytes"] == len(zip_payload)
        assert metrics["normalized_bytes"] == len(content)

    def test_csv_filename_preserved_with_directory_stripped(self):
        ((name, _, _, _),) = normalize_payload_to_csv("subdir/data.csv", CSV_SIMPLE)
        # Should preserve original source_name
        assert "data.csv" in name
