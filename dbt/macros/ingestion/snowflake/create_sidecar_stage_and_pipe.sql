{% macro snowflake__create_sidecar_stage_and_pipe(database_name, infra_schema, stage_name, storage_integration, url, file_format, pipe_name, target_table, target_schema) %}
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
        copy into {{ adapter.quote(database_name) }}.{{ adapter.quote(target_schema) }}.{{ adapter.quote(target_table) }}
        from (
            select
                $1:_contract_version::varchar as _CONTRACT_VERSION,
                $1:_downloaded_at::varchar as _DOWNLOADED_AT,
                $1:_ingested_at::varchar as _INGESTED_AT,
                $1:_source_file_path::varchar as _SOURCE_FILE_PATH,
                $1:_source_file_name::varchar as _SOURCE_FILE_NAME,
                $1:_file_content_key::varchar as _FILE_CONTENT_KEY,
                $1:_subject_period_from::varchar as _SUBJECT_PERIOD_FROM,
                $1:_subject_period_to::varchar as _SUBJECT_PERIOD_TO,
                $1:_subject_period_coverage_type::varchar as _SUBJECT_PERIOD_COVERAGE_TYPE,
                $1:_subject_period_inference_method::varchar as _SUBJECT_PERIOD_INFERENCE_METHOD,
                $1:_subject_period_inference_source::varchar as _SUBJECT_PERIOD_INFERENCE_SOURCE,
                $1:_subject_period_inference_confidence::varchar as _SUBJECT_PERIOD_INFERENCE_CONFIDENCE,
                $1:_file_scope_duration_type::varchar as _FILE_SCOPE_DURATION_TYPE,
                $1:_file_scope_duration_value::number as _FILE_SCOPE_DURATION_VALUE,
                $1:_file_scope_duration_unit::varchar as _FILE_SCOPE_DURATION_UNIT,
                $1:_file_scope_fiscal_year_start_month::number as _FILE_SCOPE_FISCAL_YEAR_START_MONTH,
                $1:_breakdown_granularity::varchar as _BREAKDOWN_GRANULARITY,
                $1:_publication_date::varchar as _PUBLICATION_DATE,
                $1:_publication_date_source::varchar as _PUBLICATION_DATE_SOURCE,
                $1:_acquisition_method::varchar as _ACQUISITION_METHOD,
                $1:_fallback_reason::varchar as _FALLBACK_REASON,
                $1:_load_id::varchar as _LOAD_ID,
                $1:_series_id::varchar as _SERIES_ID,
                $1:_sub_dataset_id::varchar as _SUB_DATASET_ID,
                $1:_target_path::varchar as _TARGET_PATH,
                $1:_payload_stage_path::varchar as _PAYLOAD_STAGE_PATH,
                $1:_source_etag::varchar as _SOURCE_ETAG,
                $1:_source_last_modified::varchar as _SOURCE_LAST_MODIFIED
            from @{{ adapter.quote(database_name) }}.{{ adapter.quote(infra_schema) }}.{{ adapter.quote(stage_name) }}
        )
        pattern = '.*_INGEST_METADATA\.json'
        file_format = {{ adapter.quote(database_name) }}.{{ adapter.quote(infra_schema) }}.{{ adapter.quote(file_format) }}
        on_error = 'CONTINUE'
    {% endset %}

    {% do run_query(create_stage) %}
    {% do run_query(create_pipe) %}
    {{ return('created sidecar stage and pipe') }}
{% endmacro %}
