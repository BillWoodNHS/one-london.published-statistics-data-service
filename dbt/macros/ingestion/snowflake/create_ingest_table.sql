{% macro snowflake__create_ingest_table(database_name, schema_name, table_name) %}
    {# Snowflake-specific: enable schema evolution #}
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
