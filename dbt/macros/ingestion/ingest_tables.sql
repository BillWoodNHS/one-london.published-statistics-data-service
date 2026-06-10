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


{% macro create_raw_dedup_view(database_name, raw_schema, raw_view, ingest_schema, ingest_table, metadata_schema=var('sidecar_metadata_schema'), metadata_table=var('sidecar_metadata_table')) %}
    {#
    Create or replace a RAW deduplication view over an INGEST table.

    The RAW view:
    - Always reflects the current state of INGEST (no lag, no refresh required)
    - Deduplicates repeated Snowpipe ingests of the same file content by keeping the
        latest copy of each row key (_FILE_CONTENT_KEY + _FILE_ROW_NUMBER)
    - LEFT JOINs to INGEST_METADATA table to pull publication date metadata
      via _SOURCE_FILE_PATH = _PAYLOAD_STAGE_PATH match
    - Replaces null publication date columns with values from sidecar metadata
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
                *
            from {{ adapter.quote(database_name) }}.{{ adapter.quote(ingest_schema) }}.{{ adapter.quote(ingest_table) }}
        ),
        with_metadata as (
            select
                p.*,
                coalesce(m._PUBLICATION_DATE, '') as _PUBLICATION_DATE,
                coalesce(m._PUBLICATION_DATE_SOURCE, 'unknown') as _PUBLICATION_DATE_SOURCE
            from parsed p
            left join {{ adapter.quote(database_name) }}.{{ adapter.quote(metadata_schema) }}.{{ adapter.quote(metadata_table) }} m
              on p._SOURCE_FILE_PATH = m._PAYLOAD_STAGE_PATH
        )
        select * exclude (_dedup_rank)
        from with_metadata
        where _dedup_rank = 1
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created or replaced raw dedup view ' ~ raw_schema ~ '.' ~ raw_view) }}
{% endmacro %}
