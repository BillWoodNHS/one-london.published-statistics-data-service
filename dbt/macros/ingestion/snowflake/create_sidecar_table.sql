{% macro snowflake__create_sidecar_table(database_name, schema_name, table_name) %}
    {% set sql %}
        create table if not exists {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(table_name) }} (
            _CONTRACT_VERSION varchar,
            _DOWNLOADED_AT varchar,
            _INGESTED_AT varchar,
            _SOURCE_FILE_PATH varchar,
            _SOURCE_FILE_NAME varchar,
            _FILE_CONTENT_KEY varchar,
            _SUBJECT_PERIOD_FROM varchar,
            _SUBJECT_PERIOD_TO varchar,
            _SUBJECT_PERIOD_COVERAGE_TYPE varchar,
            _SUBJECT_PERIOD_INFERENCE_METHOD varchar,
            _SUBJECT_PERIOD_INFERENCE_SOURCE varchar,
            _SUBJECT_PERIOD_INFERENCE_CONFIDENCE varchar,
            _FILE_SCOPE_DURATION_TYPE varchar,
            _FILE_SCOPE_DURATION_VALUE number,
            _FILE_SCOPE_DURATION_UNIT varchar,
            _FILE_SCOPE_FISCAL_YEAR_START_MONTH number,
            _BREAKDOWN_GRANULARITY varchar,
            _PUBLICATION_DATE varchar,
            _PUBLICATION_DATE_SOURCE varchar,
            _ACQUISITION_METHOD varchar,
            _FALLBACK_REASON varchar,
            _LOAD_ID varchar,
            _SERIES_ID varchar,
            _SUB_DATASET_ID varchar,
            _TARGET_PATH varchar,
            _PAYLOAD_STAGE_PATH varchar,
            _SOURCE_ETAG varchar,
            _SOURCE_LAST_MODIFIED varchar
        )
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created sidecar metadata table ' ~ schema_name ~ '.' ~ table_name) }}
{% endmacro %}
