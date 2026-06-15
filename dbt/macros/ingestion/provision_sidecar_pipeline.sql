{% macro provision_sidecar_pipeline() %}
    {#
    Provision the sidecar metadata pipeline.
    TODO: Adapter candidates should implement this macro in their own adapter-specific macro file, using the adapter dispatch pattern.
    For Snowflake: Creates metadata table, file format, stage, and Snowflake Pipe for automated ingestion.
    For DuckDB: Creates metadata table only (local files loaded via manifest-driven orchestration).
    #}
    {{ log('Provisioning sidecar metadata pipeline...', info=true) }}

    {% set database = target.database %}
    {% set infra_schema = var('infra_schema') %}
    {% set metadata_schema = var('sidecar_metadata_schema') %}
    {% set metadata_table = var('sidecar_metadata_table') %}
    {% set storage_integration = var('storage_integration_name') %}
    {% set sidecar_url = var('sidecar_metadata_blob_url') %}

    {{ create_sidecar_table(database, metadata_schema, metadata_table) }}

    {% if target.type == 'snowflake' %}
        {% if sidecar_url == '' %}
            {{ exceptions.raise_compiler_error('sidecar_metadata_blob_url required for Snowflake provisioning') }}
        {% endif %}

        {% set json_format = 'SIDECAR_JSON_FORMAT' %}
        {{ create_json_file_format(database, infra_schema, json_format) }}

        {% set stage_name = 'SIDECAR_STAGE' %}
        {% set pipe_name = 'SIDECAR_PIPE' %}
        {{ create_sidecar_stage_and_pipe(database, infra_schema, stage_name, storage_integration, sidecar_url, json_format, pipe_name, metadata_table, metadata_schema) }}

        {{ log('✓ Sidecar pipeline provisioned for Snowflake', info=true) }}
    {% elif target.type == 'duckdb' %}
        {{ log('✓ Sidecar metadata table created for DuckDB (files loaded via orchestration)', info=true) }}
    {% else %}
        {{ log('⚠ Unknown adapter type: ' ~ target.type ~ ', skipping sidecar provisioning', info=true) }}
    {% endif %}
{% endmacro %}
