{% macro snowflake__create_telemetry_stage_and_pipe(database_name, infra_schema, stage_name, storage_integration, url, file_format, pipe_name, target_table) %}
    {% set create_stage %}
        create stage if not exists {{ adapter.quote(database_name) }}.{{ adapter.quote(infra_schema) }}.{{ adapter.quote(stage_name) }}
        storage_integration = {{ adapter.quote(storage_integration) }}
        url = '{{ url }}'
        file_format = {{ adapter.quote(database_name) }}.{{ adapter.quote(infra_schema) }}.{{ adapter.quote(file_format) }}
    {% endset %}

    {% set create_pipe %}
        create pipe if not exists {{ adapter.quote(database_name) }}.{{ adapter.quote(infra_schema) }}.{{ adapter.quote(pipe_name) }}
        auto_ingest = true
        as
        copy into {{ adapter.quote(database_name) }}.{{ adapter.quote(var('raw_schema')) }}.{{ adapter.quote(target_table) }}
        from (
            select
                to_timestamp_ntz($1:event_timestamp_utc::string) as EVENT_TIMESTAMP_UTC,
                $1:run_id::string as RUN_ID,
                $1:contract_version::string as CONTRACT_VERSION,
                $1:stage::string as STAGE,
                $1:status::string as STATUS,
                $1:attempt_number::number as ATTEMPT_NUMBER,
                $1:series_id::string as SERIES_ID,
                $1:sub_dataset_id::string as SUB_DATASET_ID,
                $1:source_url::string as SOURCE_URL,
                $1:file_name::string as FILE_NAME,
                $1:source_content_hash::string as SOURCE_CONTENT_HASH,
                $1:load_id::string as LOAD_ID,
                $1:source_bytes::number as SOURCE_BYTES,
                $1:raw_row_count::number as RAW_ROW_COUNT,
                $1:normalized_row_count::number as NORMALIZED_ROW_COUNT,
                $1:normalized_bytes::number as NORMALIZED_BYTES,
                $1:uploaded_path::string as UPLOADED_PATH,
                $1:skip_reason::string as SKIP_REASON,
                $1:acquisition_method::string as ACQUISITION_METHOD,
                $1:duration_ms::number as DURATION_MS,
                $1:error_type::string as ERROR_TYPE,
                $1:error_message::string as ERROR_MESSAGE,
                $1:discovered_file_count::number as DISCOVERED_FILE_COUNT
            from @{{ adapter.quote(database_name) }}.{{ adapter.quote(infra_schema) }}.{{ adapter.quote(stage_name) }}
        )
        file_format = {{ adapter.quote(database_name) }}.{{ adapter.quote(infra_schema) }}.{{ adapter.quote(file_format) }}
        on_error = 'CONTINUE'
    {% endset %}

    {% do run_query(create_stage) %}
    {% do run_query(create_pipe) %}
    {{ return('created telemetry stage and pipe') }}
{% endmacro %}
