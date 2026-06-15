{% macro provision_target_pipeline(series_id, sub_dataset_id, target_cfg) %}
    {#
    Provision the ingestion infrastructure for a single target.

    Creates:
    - DuckDB: Ingest table, raw dedup view
    - Snowflake: File format, stage, Snowflake Pipe, ingest table, raw dedup view
    #}
    {% set database = target.database %}
    {% set ingest_schema = var('ingest_schema') %}
    {% set raw_schema = var('raw_schema') %}
    {% set infra_schema = var('infra_schema') %}
    {% set storage_integration = var('storage_integration_name') %}
    {% set adls_url_root = var('adls_url_root') %}

    {% set object_suffix = target_cfg['object_name_suffix'] %}
    {% set ingest_table = 'INGEST_' ~ object_suffix %}
    {% set raw_view = 'RAW_' ~ object_suffix %}
    {% set file_format = 'CSV_FORMAT_' ~ object_suffix %}
    {% set stage_name = 'STAGE_' ~ object_suffix %}
    {% set pipe_name = 'PIPE_' ~ object_suffix %}
    {% set blob_url = (adls_url_root.rstrip('/') ~ '/' ~ target_cfg['adls_path_prefix'].strip('/') ~ '/') if adls_url_root != '' else '' %}

    {{ log('Provisioning pipeline for ' ~ object_suffix, info=true) }}

    {{ create_ingest_table(database, ingest_schema, ingest_table) }}
    {{ create_raw_dedup_view(database, raw_schema, raw_view, ingest_schema, ingest_table) }}

    {% if target.type == 'snowflake' %}
        {% if blob_url == '' %}
            {{ exceptions.raise_compiler_error('blob_url required for Snowflake target ' ~ object_suffix) }}
        {% endif %}

        {{ create_csv_file_format(database, infra_schema, file_format) }}
        {{ create_stage_and_pipe(database, infra_schema, stage_name, storage_integration, blob_url, file_format, pipe_name, ingest_table, ingest_schema) }}

        {{ log('✓ Complete pipeline provisioned for ' ~ object_suffix, info=true) }}
    {% elif target.type == 'duckdb' %}
        {{ log('✓ Local pipeline provisioned for ' ~ object_suffix, info=true) }}
    {% endif %}
{% endmacro %}
