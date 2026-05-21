from tests.dbt_macro_harness import render_alias_select_sql, require_dbt

import pytest


duckdb = pytest.importorskip("duckdb")


def test_duckdb_projection_matches_aliasing_expectation(tmp_path):
    require_dbt()

    query_duckdb_path = tmp_path / "aliasing_query.duckdb"
    macro_duckdb_path = tmp_path / "aliasing_macro.duckdb"
    con = duckdb.connect(database=str(query_duckdb_path))
    con.execute('create table raw_data ("A b" integer, "c-d" integer, "_PUBLICATION_DATE" varchar)')
    con.execute("insert into raw_data values (1, 2, '20260519T103600')")

    select_sql = render_alias_select_sql(["A b", "c-d", "_PUBLICATION_DATE"], macro_duckdb_path)
    row = con.execute(f"select {select_sql} from raw_data").fetchone()

    assert row == (1, 2, "20260519T103600")


def test_acronyms_remain_intact_in_aliasing(tmp_path):
    require_dbt()

    query_duckdb_path = tmp_path / "acronyms_query.duckdb"
    macro_duckdb_path = tmp_path / "acronyms_macro.duckdb"
    con = duckdb.connect(database=str(query_duckdb_path))
    con.execute('create table raw_data ("NHSNumber" integer, "ODSCode" integer, "XMLParserVersion" integer)')
    con.execute("insert into raw_data values (1, 2, 3)")

    select_sql = render_alias_select_sql(["NHSNumber", "ODSCode", "XMLParserVersion"], macro_duckdb_path)
    con.execute(f"create view presentation_view as select {select_sql} from raw_data")
    columns = [row[1] for row in con.execute("PRAGMA table_info('presentation_view')").fetchall()]

    assert columns == ["NHS_NUMBER", "ODS_CODE", "XML_PARSER_VERSION"]
