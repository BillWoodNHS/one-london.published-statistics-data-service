{% macro create_csv_file_format(database_name, schema_name, file_format_name) %}
    {% set sql %}
        create file format if not exists {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(file_format_name) }}
        type = csv
        field_delimiter = ','
        skip_header = 1
        parse_header = true
        field_optionally_enclosed_by = '"'
        empty_field_as_null = true
        trim_space = true
    {% endset %}
    {% do run_query(sql) %}
    {{ return('created file format ' ~ schema_name ~ '.' ~ file_format_name) }}
{% endmacro %}


{% macro create_ingest_table(database_name, schema_name, table_name) %}
    {#
    Create an INGEST table that receives Snowpipe loads directly.
    
    INGEST tables:
    - Receive all file uploads (including re-uploads/duplicates)
    - Preserve full audit trail via metadata columns
    - Auto-evolve schema as new columns appear in CSV files
    - Deduplicated downstream by RAW views
    #}
    
    {% set sql %}
        create table if not exists {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(table_name) }} (
            _INGESTED_AT timestamp_ntz,
            _SOURCE_FILE_PATH varchar,
            _SOURCE_FILE_NAME varchar,
            _FILE_ROW_NUMBER number,
            _FILE_CONTENT_KEY varchar,
            _PUBLICATION_DATE varchar,
            _ACQUISITION_METHOD varchar default 'automated',
            _FALLBACK_REASON varchar default '',
            _LOAD_ID varchar
        )
        enable_schema_evolution = true
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created ingest table ' ~ schema_name ~ '.' ~ table_name) }}
{% endmacro %}


{% macro create_raw_table(database_name, schema_name, table_name) %}
    {# Deprecated: Use create_ingest_table instead. This macro is kept for backwards compatibility. #}
    {{ return(one_london_psds.create_ingest_table(database_name, schema_name, table_name)) }}
{% endmacro %}


{% macro create_raw_dedup_view(database_name, raw_schema, raw_view, ingest_schema, ingest_table) %}
    {#
    Create or replace a RAW deduplication view over an INGEST table.

    The RAW view:
    - Always reflects the current state of INGEST (no lag, no refresh required)
        - Deduplicates repeated Snowpipe ingests of the same file content by keeping the
            latest copy of each row key (_FILE_CONTENT_KEY + _FILE_ROW_NUMBER)
    - Derives _PUBLICATION_DATE and _PUBLICATION_DATE_SOURCE from _SOURCE_FILE_PATH by
      parsing the embedded prefix written by the function app:
        scraped-YYYYMMDDTHHMMSS  →  date scraped from the publisher page
        ingest-YYYYMMDDTHHMMSS   →  download timestamp used as fallback
    - Replaces the always-NULL _PUBLICATION_DATE column from INGEST with the derived value
    - Is safe to re-run: CREATE OR REPLACE is idempotent
    - Can be promoted to a Dynamic Table later if query performance requires it

    Called by provision_target_pipeline as part of the standard dataset provisioning workflow.
    #}

    {% set sql %}
        create or replace view {{ adapter.quote(database_name) }}.{{ adapter.quote(raw_schema) }}.{{ adapter.quote(raw_view) }} as
        with
        parsed as (
            select
                row_number() over (
                    partition by _FILE_CONTENT_KEY, _FILE_ROW_NUMBER
                    order by _INGESTED_AT desc
                ) as _dedup_rank,
                regexp_substr(_SOURCE_FILE_PATH, 'publication_date=([^/]+)/', 1, 1, 'e') as _pub_raw,
                * exclude (_PUBLICATION_DATE)
            from {{ adapter.quote(database_name) }}.{{ adapter.quote(ingest_schema) }}.{{ adapter.quote(ingest_table) }}
        ),
        ranked as (
            select
                _dedup_rank,
                case
                    when _pub_raw like 'scraped-%' then substr(_pub_raw, 9)
                    when _pub_raw like 'ingest-%'  then substr(_pub_raw, 8)
                    else _pub_raw
                end as _PUBLICATION_DATE,
                case
                    when _pub_raw like 'scraped-%' then 'scraped'
                    when _pub_raw like 'ingest-%'  then 'ingest-fallback'
                    else 'unknown'
                end as _PUBLICATION_DATE_SOURCE,
                * exclude (_dedup_rank, _pub_raw)
            from parsed
        )
        select * exclude (_dedup_rank)
        from ranked
        where _dedup_rank = 1
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created or replaced raw dedup view ' ~ raw_schema ~ '.' ~ raw_view) }}
{% endmacro %}
