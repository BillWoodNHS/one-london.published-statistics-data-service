{% macro snowflake__create_telemetry_raw_table(database_name, schema_name, table_name) %}
    {% set sql %}
        create table if not exists {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(table_name) }} (
            EVENT_TIMESTAMP_UTC timestamp_ntz,
            RUN_ID varchar,
            CONTRACT_VERSION varchar,
            STAGE varchar,
            STATUS varchar,
            ATTEMPT_NUMBER number,
            SERIES_ID varchar,
            SUB_DATASET_ID varchar,
            SOURCE_URL varchar,
            FILE_NAME varchar,
            SOURCE_CONTENT_HASH varchar,
            LOAD_ID varchar,
            SOURCE_BYTES number,
            RAW_ROW_COUNT number,
            NORMALIZED_ROW_COUNT number,
            NORMALIZED_BYTES number,
            UPLOADED_PATH varchar,
            SKIP_REASON varchar,
            ACQUISITION_METHOD varchar,
            DURATION_MS number,
            ERROR_TYPE varchar,
            ERROR_MESSAGE varchar,
            DISCOVERED_FILE_COUNT number
        )
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created telemetry table ' ~ schema_name ~ '.' ~ table_name) }}
{% endmacro %}
