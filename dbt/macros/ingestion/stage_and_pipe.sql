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
