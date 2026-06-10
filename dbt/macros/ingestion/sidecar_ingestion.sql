{% macro create_sidecar_table(database_name, schema_name, table_name) %}
    {% set sql %}
        create table if not exists {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(table_name) }} (
            _CONTRACT_VERSION varchar,
            _DOWNLOADED_AT varchar,
            _INGESTED_AT varchar,
            _SOURCE_FILE_PATH varchar,
            _SOURCE_FILE_NAME varchar,
            _FILE_CONTENT_KEY varchar,
            _SUBJECT_PERIOD varchar,
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


{% macro create_sidecar_stage_and_pipe(database_name, infra_schema, stage_name, storage_integration, url, file_format, pipe_name, target_table, target_schema) %}
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
                $1:_subject_period::varchar as _SUBJECT_PERIOD,
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


{% macro provision_sidecar_pipeline(database_name=target.database, infra_schema=var('infra_schema'), ingest_schema=var('ingest_schema')) %}
    {% set adls_url_root = var('adls_url_root') %}
    {% set storage_integration_name = var('storage_integration_name') %}
    {% set telemetry_file_format_name = var('telemetry_file_format_name') %}

    {% if adls_url_root == '' %}
        {{ exceptions.raise_compiler_error('adls_url_root var is required for sidecar provisioning.') }}
    {% endif %}

    {% set sidecar_url = adls_url_root.rstrip('/') ~ '/' %}

    {% do one_london_psds.create_storage_integration(storage_integration_name, adls_url_root, var('managed_identity_tenant_id')) %}
    {% do one_london_psds.create_json_file_format(database_name, infra_schema, telemetry_file_format_name) %}
    {% do one_london_psds.create_sidecar_table(database_name, ingest_schema, 'INGEST_METADATA') %}
    {% do one_london_psds.create_sidecar_stage_and_pipe(
        database_name,
        infra_schema,
        'STG_SIDECAR',
        storage_integration_name,
        sidecar_url,
        telemetry_file_format_name,
        'PIPE_SIDECAR',
        'INGEST_METADATA',
        target_schema=ingest_schema
    ) %}

    {{ return({'sidecar_url': sidecar_url}) }}
{% endmacro %}
