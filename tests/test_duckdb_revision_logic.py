import pytest

duckdb = pytest.importorskip("duckdb")


def test_latest_publication_per_reporting_period_duckdb():
    con = duckdb.connect(database=":memory:")

    con.execute(
        """
        create table raw_data (
            REPORTING_PERIOD varchar,
            VALUE integer,
            _PUBLICATION_DATE varchar,
            _SUBJECT_PERIOD_TO varchar,
            _DOWNLOADED_AT varchar,
            _INGESTED_AT varchar,
            _SOURCE_FILE_PATH varchar
        )
        """
    )

    con.execute(
        """
        insert into raw_data values
            (
                '2026-01', 10, '20260115T090000', '20260131T235959',
                '20260216T090000', '2026-02-16T09:00:00', 'series/jan_v1.csv'
            ),
            (
                '2026-01', 11, '20260216T090000', '20260131T235959',
                '20260216T090100', '2026-02-16T09:01:00', 'series/jan_v2.csv'
            ),
            (
                '2026-02', 20, '20260216T090000', '20260228T235959',
                '20260318T090000', '2026-03-18T09:00:00', 'series/feb_v1.csv'
            ),
            (
                '2026-02', 21, '20260318T090000', '20260228T235959',
                '20260318T090500', '2026-03-18T09:05:00', 'series/feb_v2.csv'
            )
        """
    )

    con.execute(
        """
        create view v_max_publication as
        with ranked as (
            select
                REPORTING_PERIOD,
                _PUBLICATION_DATE,
                _SUBJECT_PERIOD_TO,
                _DOWNLOADED_AT,
                _INGESTED_AT,
                _SOURCE_FILE_PATH,
                row_number() over (
                    partition by REPORTING_PERIOD
                    order by
                        case when _PUBLICATION_DATE = '' then 0 else 1 end desc,
                        _PUBLICATION_DATE desc,
                        case when _SUBJECT_PERIOD_TO = '' then 0 else 1 end desc,
                        _SUBJECT_PERIOD_TO desc,
                        _DOWNLOADED_AT desc,
                        _INGESTED_AT desc,
                        _SOURCE_FILE_PATH desc
                ) as _revision_rank
            from raw_data
        )
        select
            REPORTING_PERIOD,
            _PUBLICATION_DATE as MAX_PUBLICATION_DATE,
            _SUBJECT_PERIOD_TO as MAX_SUBJECT_PERIOD_TO,
            _DOWNLOADED_AT as MAX_DOWNLOADED_AT,
            _INGESTED_AT as MAX_INGESTED_AT,
            _SOURCE_FILE_PATH as MAX_SOURCE_FILE_PATH
        from ranked
        where _revision_rank = 1
        """
    )

    rows = con.execute(
        """
                select src.REPORTING_PERIOD, src.VALUE, src._PUBLICATION_DATE
        from raw_data src
        join v_max_publication mx
          on src.REPORTING_PERIOD = mx.REPORTING_PERIOD
         and src._PUBLICATION_DATE = mx.MAX_PUBLICATION_DATE
                 and src._SUBJECT_PERIOD_TO = mx.MAX_SUBJECT_PERIOD_TO
                 and src._DOWNLOADED_AT = mx.MAX_DOWNLOADED_AT
                 and src._INGESTED_AT = mx.MAX_INGESTED_AT
                 and src._SOURCE_FILE_PATH = mx.MAX_SOURCE_FILE_PATH
        order by src.REPORTING_PERIOD
        """
    ).fetchall()

    assert rows == [
        ("2026-01", 11, "20260216T090000"),
        ("2026-02", 21, "20260318T090000"),
    ]


def test_revision_tiebreak_prefers_later_subject_period_to_before_downloaded_at():
    con = duckdb.connect(database=":memory:")

    con.execute(
        """
        create table raw_data (
            REPORTING_PERIOD varchar,
            VALUE integer,
            _PUBLICATION_DATE varchar,
            _SUBJECT_PERIOD_TO varchar,
            _DOWNLOADED_AT varchar,
            _INGESTED_AT varchar,
            _SOURCE_FILE_PATH varchar
        )
        """
    )

    con.execute(
        """
        insert into raw_data values
            (
                '2026-04', 101, '20260620T090000', '20260531T235959',
                '20260620T101500', '2026-06-20T10:15:00', 'series/up_to_may.csv'
            ),
            (
                '2026-04', 202, '20260620T090000', '20260630T235959',
                '20260620T101000', '2026-06-20T10:10:00', 'series/up_to_june.csv'
            )
        """
    )

    rows = con.execute(
        """
        with ranked as (
            select
                *,
                row_number() over (
                    partition by REPORTING_PERIOD
                    order by
                        case when _PUBLICATION_DATE = '' then 0 else 1 end desc,
                        _PUBLICATION_DATE desc,
                        case when _SUBJECT_PERIOD_TO = '' then 0 else 1 end desc,
                        _SUBJECT_PERIOD_TO desc,
                        _DOWNLOADED_AT desc,
                        _INGESTED_AT desc,
                        _SOURCE_FILE_PATH desc
                ) as _revision_rank
            from raw_data
        )
        select REPORTING_PERIOD, VALUE
        from ranked
        where _revision_rank = 1
        """
    ).fetchall()

    assert rows == [("2026-04", 202)]


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
