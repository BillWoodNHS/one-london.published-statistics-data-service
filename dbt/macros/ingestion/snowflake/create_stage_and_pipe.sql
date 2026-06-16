{% macro snowflake__create_stage_and_pipe(database_name, schema_name, stage_name, storage_integration, url, file_format, pipe_name, target_table, target_schema, pattern='.*\\.csv') %}
    {% set create_stage %}
        create stage if not exists {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(stage_name) }}
        storage_integration = {{ adapter.quote(storage_integration) }}
        url = '{{ url }}'
        file_format = {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(file_format) }}
    {% endset %}

    {% set create_pipe %}
        create pipe if not exists {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(pipe_name) }}
        auto_ingest = true
        as
        copy into {{ adapter.quote(database_name) }}.{{ adapter.quote(target_schema) }}.{{ adapter.quote(target_table) }}
        from @{{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(stage_name) }}
        match_by_column_name = case_insensitive
        include_metadata = (
            _INGESTED_AT = metadata$start_scan_time,
            _SOURCE_FILE_PATH = metadata$filename,
            _SOURCE_FILE_NAME = metadata$filename,
            _FILE_ROW_NUMBER = metadata$file_row_number,
            _FILE_CONTENT_KEY = metadata$file_content_key,
            _LOAD_ID = metadata$file_content_key
        )
        pattern = '{{ pattern }}'
        on_error = 'CONTINUE'
    {% endset %}

    {% do run_query(create_stage) %}
    {% do run_query(create_pipe) %}
    {{ return('created stage and pipe for ' ~ target_table) }}
{% endmacro %}
