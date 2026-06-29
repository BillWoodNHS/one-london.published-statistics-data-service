import pytest

from tests.dbt_macro_harness import render_presentation_view_columns, require_dbt

duckdb = pytest.importorskip("duckdb")


def test_create_presentation_view_aliases_columns(tmp_path):
    require_dbt()

    duckdb_path = tmp_path / "presentation_aliasing.duckdb"

    expected_columns = [
        "NHS_NUMBER",
        "A_B",
        "_SUBJECT_PERIOD_FROM",
        "_SUBJECT_PERIOD_TO",
        "_LOADED_AT",
    ]

    columns = render_presentation_view_columns(
        raw_schema="RAW",
        raw_table="RAW_TEST",
        view_name="PRESENTATION_TEST",
        column_names=["NHSNumber", "A b", "_SUBJECT_PERIOD_FROM", "_SUBJECT_PERIOD_TO"],
        duckdb_file=duckdb_path,
    )

    assert columns == expected_columns

    # The dbt run-operation process has exited by this point. Re-open the DuckDB file
    # independently to confirm the view was actually committed to disk, not just visible
    # within the run-operation's own (possibly uncommitted) session.
    con = duckdb.connect(str(duckdb_path), read_only=True)
    table_info = con.execute("PRAGMA table_info('RAW.PRESENTATION_TEST')").fetchall()
    persisted_columns = [row[1] for row in table_info]
    assert persisted_columns == expected_columns
