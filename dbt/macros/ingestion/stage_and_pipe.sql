{% macro create_stage_and_pipe(database_name, schema_name, stage_name, storage_integration, url, file_format, pipe_name, target_table, target_schema, pattern='.*\\.csv') %}
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


{% macro provision_target_pipeline(database_name, infra_schema, ingest_schema, raw_schema, series_id, sub_dataset_id, object_name_suffix, adls_path_prefix, adls_url_root, storage_integration_name, file_format_name) %}
    {% if object_name_suffix == '' %}
        {{ exceptions.raise_compiler_error('object_name_suffix is required for provisioning target ' ~ series_id ~ '/' ~ sub_dataset_id) }}
    {% endif %}
    {% if adls_path_prefix == '' %}
        {{ exceptions.raise_compiler_error('adls_path_prefix is required for provisioning target ' ~ series_id ~ '/' ~ sub_dataset_id) }}
    {% endif %}

    {% set stage_name = 'STG_' ~ object_name_suffix %}
    {% set ingest_table_name = 'INGEST_' ~ object_name_suffix %}
    {% set raw_table_name = 'RAW_' ~ object_name_suffix %}
    {% set pipe_name = 'PIPE_' ~ object_name_suffix %}
    {% set target_url = adls_url_root.rstrip('/') ~ '/' ~ adls_path_prefix ~ '/' %}

    {% do one_london_psds.create_ingest_table(database_name, ingest_schema, ingest_table_name) %}
    {% do one_london_psds.create_stage_and_pipe(
        database_name,
        infra_schema,
        stage_name,
        storage_integration_name,
        target_url,
        file_format_name,
        pipe_name,
        ingest_table_name,
        target_schema=ingest_schema,
        pattern='.*\\.csv'
    ) %}
    {% do one_london_psds.create_raw_dedup_view(
        database_name,
        raw_schema,
        raw_table_name,
        ingest_schema,
        ingest_table_name,
        metadata_schema=var('sidecar_metadata_schema'),
        metadata_table=var('sidecar_metadata_table')
    ) %}

    {{ return({'stage': stage_name, 'pipe': pipe_name, 'ingest_table': ingest_table_name, 'raw_view': raw_table_name, 'url': target_url}) }}
{% endmacro %}


{% macro provision_series_from_manifest(manifest_path, database_name=target.database, infra_schema=var('infra_schema'), ingest_schema=var('ingest_schema'), raw_schema=var('raw_schema')) %}
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
            ingest_schema,
            raw_schema,
            series_id,
            target_cfg['sub_dataset_id'],
            target_cfg['object_name_suffix'],
            target_cfg['adls_path_prefix'],
            adls_url_root,
            storage_integration_name,
            file_format_name
        ) %}
        {% do outputs.append(result) %}
    {% endfor %}

    {{ return(outputs) }}
{% endmacro %}
