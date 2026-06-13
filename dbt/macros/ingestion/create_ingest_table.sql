{% macro create_ingest_table(database_name, schema_name, table_name) %}
    {{ return(adapter.dispatch('create_ingest_table')(database_name, schema_name, table_name)) }}
{% endmacro %}

{% macro default__create_ingest_table(database_name, schema_name, table_name) %}
    {# Generic implementation for DuckDB #}
    {% set sql %}
        create schema if not exists {{ adapter.quote(schema_name) }};
        create table if not exists {{ adapter.quote(schema_name) }}.{{ adapter.quote(table_name) }} (
            _INGESTED_AT timestamp,
            _SOURCE_FILE_PATH varchar,
            _SOURCE_FILE_NAME varchar,
            _FILE_ROW_NUMBER bigint,
            _FILE_CONTENT_KEY varchar,
            _ACQUISITION_METHOD varchar,
            _FALLBACK_REASON varchar,
            _LOAD_ID varchar
        )
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created ingest table ' ~ schema_name ~ '.' ~ table_name) }}
{% endmacro %}
