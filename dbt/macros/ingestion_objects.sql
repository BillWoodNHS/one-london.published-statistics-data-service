{% macro normalize_identifier(value) %}
    {% set cleaned = value | replace('-', '_') | replace(' ', '_') | replace('/', '_') %}
    {{ return(cleaned | upper) }}
{% endmacro %}


{% macro create_storage_integration(storage_integration_name, allowed_location, tenant_id) %}
    {% set sql %}
        create storage integration if not exists {{ adapter.quote(storage_integration_name) }}
        type = external_stage
        storage_provider = azure
        enabled = true
        azure_tenant_id = '{{ tenant_id }}'
        storage_allowed_locations = ('{{ allowed_location }}')
        comment = 'Managed by dbt for published statistics service'
    {% endset %}

    {% if tenant_id == '' %}
        {{ exceptions.raise_compiler_error('managed_identity_tenant_id must be provided via vars.') }}
    {% endif %}

    {% do run_query(sql) %}
    {{ return('created storage integration ' ~ storage_integration_name) }}
{% endmacro %}


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


{% macro create_raw_table(database_name, schema_name, table_name) %}
    {% set sql %}
        create table if not exists {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(table_name) }} (
            _INGESTED_AT timestamp_ntz,
            _SOURCE_FILE_PATH varchar,
            _SOURCE_FILE_NAME varchar,
            _FILE_ROW_NUMBER number,
            _FILE_CONTENT_KEY varchar,
            _PUBLICATION_DATE varchar,
            _ACQUISITION_METHOD varchar default 'automated',
            _FALLBACK_REASON varchar default '',
            _LOAD_ID varchar
        )
        enable_schema_evolution = true
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created raw table ' ~ schema_name ~ '.' ~ table_name) }}
{% endmacro %}


{% macro create_stage_and_pipe(database_name, schema_name, stage_name, storage_integration, url, file_format, pipe_name, target_table, pattern='.*') %}
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
        copy into {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(target_table) }}
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


{% macro provision_target_pipeline(database_name, infra_schema, raw_schema, series_id, sub_dataset_id, adls_url_root, storage_integration_name, file_format_name) %}
    {% set series_token = one_london_psds.normalize_identifier(series_id) %}
    {% set sub_token = one_london_psds.normalize_identifier(sub_dataset_id) %}

    {% set stage_name = 'STG_' ~ series_token ~ '_' ~ sub_token %}
    {% set table_name = 'RAW_' ~ series_token ~ '_' ~ sub_token %}
    {% set pipe_name = 'PIPE_' ~ series_token ~ '_' ~ sub_token %}
    {% set target_url = adls_url_root.rstrip('/') ~ '/' ~ series_id ~ '/' ~ sub_dataset_id ~ '/' %}

    {% do one_london_psds.create_raw_table(database_name, raw_schema, table_name) %}
    {% do one_london_psds.create_stage_and_pipe(
        database_name,
        infra_schema,
        stage_name,
        storage_integration_name,
        target_url,
        file_format_name,
        pipe_name,
        table_name
    ) %}

    {{ return({'stage': stage_name, 'pipe': pipe_name, 'table': table_name, 'url': target_url}) }}
{% endmacro %}


{% macro provision_series_from_manifest(manifest_path, database_name=target.database, infra_schema=var('infra_schema'), raw_schema=var('raw_schema')) %}
    {% set manifest = fromyaml(read_file(manifest_path)) %}

    {% if manifest is none %}
        {{ exceptions.raise_compiler_error('Failed to parse manifest at ' ~ manifest_path) }}
    {% endif %}

    {% set series_id = manifest['series_id'] %}
    {% set targets = manifest['targets'] %}
    {% set adls_url_root = var('adls_url_root') %}
    {% set storage_integration_name = var('storage_integration_name') %}
    {% set file_format_name = var('file_format_name') %}
    {% set tenant_id = var('managed_identity_tenant_id') %}

    {% if adls_url_root == '' %}
        {{ exceptions.raise_compiler_error('adls_url_root var is required for Snowflake provisioning.') }}
    {% endif %}

    {% do one_london_psds.create_storage_integration(storage_integration_name, adls_url_root, tenant_id) %}
    {% do one_london_psds.create_csv_file_format(database_name, infra_schema, file_format_name) %}

    {% set outputs = [] %}
    {% for target_cfg in targets %}
        {% set result = one_london_psds.provision_target_pipeline(
            database_name,
            infra_schema,
            raw_schema,
            series_id,
            target_cfg['sub_dataset_id'],
            adls_url_root,
            storage_integration_name,
            file_format_name
        ) %}
        {% do outputs.append(result) %}
    {% endfor %}

    {{ return(outputs) }}
{% endmacro %}


{% macro create_json_file_format(database_name, schema_name, file_format_name) %}
    {% set sql %}
        create file format if not exists {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(file_format_name) }}
        type = json
        strip_outer_array = false
    {% endset %}
    {% do run_query(sql) %}
    {{ return('created json file format ' ~ schema_name ~ '.' ~ file_format_name) }}
{% endmacro %}


{% macro create_telemetry_raw_table(database_name, schema_name, table_name) %}
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


{% macro create_telemetry_stage_and_pipe(database_name, infra_schema, stage_name, storage_integration, url, file_format, pipe_name, target_table) %}
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


{% macro provision_telemetry_pipeline(database_name=target.database, infra_schema=var('infra_schema'), raw_schema=var('raw_schema')) %}
    {% set adls_url_root = var('adls_url_root') %}
    {% set telemetry_prefix = var('telemetry_prefix') %}
    {% set storage_integration_name = var('storage_integration_name') %}
    {% set telemetry_file_format_name = var('telemetry_file_format_name') %}

    {% if adls_url_root == '' %}
        {{ exceptions.raise_compiler_error('adls_url_root var is required for telemetry provisioning.') }}
    {% endif %}

    {% set telemetry_url = adls_url_root.rstrip('/') ~ '/' ~ telemetry_prefix.strip('/') ~ '/' %}

    {% do one_london_psds.create_storage_integration(storage_integration_name, adls_url_root, var('managed_identity_tenant_id')) %}
    {% do one_london_psds.create_json_file_format(database_name, infra_schema, telemetry_file_format_name) %}
    {% do one_london_psds.create_telemetry_raw_table(database_name, raw_schema, 'RAW_FUNCTION_APP_EVENTS') %}
    {% do one_london_psds.create_telemetry_stage_and_pipe(
        database_name,
        infra_schema,
        'STG_FUNCTION_APP_EVENTS',
        storage_integration_name,
        telemetry_url,
        telemetry_file_format_name,
        'PIPE_FUNCTION_APP_EVENTS',
        'RAW_FUNCTION_APP_EVENTS'
    ) %}

    {{ return({'telemetry_url': telemetry_url}) }}
{% endmacro %}
