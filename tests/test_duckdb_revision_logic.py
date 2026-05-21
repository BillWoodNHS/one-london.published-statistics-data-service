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
