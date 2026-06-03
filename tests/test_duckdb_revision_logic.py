import pytest

duckdb = pytest.importorskip("duckdb")


def test_latest_publication_per_reporting_period_duckdb():
    con = duckdb.connect(database=":memory:")

    con.execute(
        """
        create table raw_data (
            REPORTING_PERIOD varchar,
            VALUE integer,
            _PUBLICATION_DATE varchar
        )
        """
    )

    con.execute(
        """
        insert into raw_data values
            ('2026-01', 10, '20260115T090000'),
            ('2026-01', 11, '20260216T090000'),
            ('2026-02', 20, '20260216T090000'),
            ('2026-02', 21, '20260318T090000')
        """
    )

    con.execute(
        """
        create view v_max_publication as
        select
            REPORTING_PERIOD,
            max(_PUBLICATION_DATE) as MAX_PUBLICATION_DATE
        from raw_data
        group by REPORTING_PERIOD
        """
    )

    rows = con.execute(
        """
        select src.REPORTING_PERIOD, src.VALUE, src._PUBLICATION_DATE
        from raw_data src
        join v_max_publication mx
          on src.REPORTING_PERIOD = mx.REPORTING_PERIOD
         and src._PUBLICATION_DATE = mx.MAX_PUBLICATION_DATE
        order by src.REPORTING_PERIOD
        """
    ).fetchall()

    assert rows == [
        ("2026-01", 11, "20260216T090000"),
        ("2026-02", 21, "20260318T090000"),
    ]


def test_raw_dedup_keeps_one_copy_per_row_key_and_all_rows_per_file_duckdb():
    con = duckdb.connect(database=":memory:")

    con.execute(
        """
        create table ingest_data (
            _INGESTED_AT timestamp,
            _SOURCE_FILE_PATH varchar,
            _FILE_CONTENT_KEY varchar,
            _FILE_ROW_NUMBER integer,
            VALUE integer
        )
        """
    )

    # Same file content (hash-1) ingested twice; each ingest has 3 rows.
    # A second, distinct file (hash-2) has 2 rows.
    con.execute(
        """
        insert into ingest_data values
            ('2026-06-01 09:00:00', 'series/a.csv', 'hash-1', 1, 101),
            ('2026-06-01 09:00:00', 'series/a.csv', 'hash-1', 2, 102),
            ('2026-06-01 09:00:00', 'series/a.csv', 'hash-1', 3, 103),
            ('2026-06-01 10:00:00', 'series/a.csv', 'hash-1', 1, 101),
            ('2026-06-01 10:00:00', 'series/a.csv', 'hash-1', 2, 102),
            ('2026-06-01 10:00:00', 'series/a.csv', 'hash-1', 3, 103),
            ('2026-06-01 11:00:00', 'series/b.csv', 'hash-2', 1, 201),
            ('2026-06-01 11:00:00', 'series/b.csv', 'hash-2', 2, 202)
        """
    )

    con.execute(
        """
        create view raw_dedup as
        with ranked as (
            select
                row_number() over (
                    partition by _FILE_CONTENT_KEY, _FILE_ROW_NUMBER
                    order by _INGESTED_AT desc
                ) as _dedup_rank,
                *
            from ingest_data
        )
        select * exclude (_dedup_rank)
        from ranked
        where _dedup_rank = 1
        """
    )

    # Requirement 1: exactly one row per row key
    unique_key_count = con.execute(
        """
        select count(*)
        from (
            select distinct _FILE_CONTENT_KEY, _FILE_ROW_NUMBER
            from ingest_data
        ) keys
        """
    ).fetchone()[0]
    dedup_count = con.execute("select count(*) from raw_dedup").fetchone()[0]
    assert dedup_count == unique_key_count

    # Requirement 2: multi-row file remains complete (all 3 rows for hash-1)
    hash_1_rows = con.execute(
        """
        select _FILE_ROW_NUMBER, VALUE
        from raw_dedup
        where _FILE_CONTENT_KEY = 'hash-1'
        order by _FILE_ROW_NUMBER
        """
    ).fetchall()
    assert hash_1_rows == [(1, 101), (2, 102), (3, 103)]
