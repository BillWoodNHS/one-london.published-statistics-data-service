{% macro create_telemetry_raw_table(database_name, schema_name, table_name) %}
    {{ return(adapter.dispatch('create_telemetry_raw_table')(database_name, schema_name, table_name)) }}
{% endmacro %}

{% macro default__create_telemetry_raw_table(database_name, schema_name, table_name) %}
    {# Generic DuckDB implementation #}
    {% set sql %}
        create schema if not exists {{ adapter.quote(schema_name) }};
        create table if not exists {{ adapter.quote(schema_name) }}.{{ adapter.quote(table_name) }} (
            EVENT_TIMESTAMP_UTC timestamp,
            RUN_ID varchar,
            CONTRACT_VERSION varchar,
            STAGE varchar,
            STATUS varchar,
            ATTEMPT_NUMBER bigint,
            SERIES_ID varchar,
            SUB_DATASET_ID varchar,
            SOURCE_URL varchar,
            FILE_NAME varchar,
            SOURCE_CONTENT_HASH varchar,
            LOAD_ID varchar,
            SOURCE_BYTES bigint,
            RAW_ROW_COUNT bigint,
            NORMALIZED_ROW_COUNT bigint,
            NORMALIZED_BYTES bigint,
            UPLOADED_PATH varchar,
            SKIP_REASON varchar,
            ACQUISITION_METHOD varchar,
            DURATION_MS bigint,
            ERROR_TYPE varchar,
            ERROR_MESSAGE varchar,
            DISCOVERED_FILE_COUNT bigint
        )
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created telemetry table ' ~ schema_name ~ '.' ~ table_name) }}
{% endmacro %}
