{% macro provision_telemetry_pipeline() %}
    {#
    Provision the telemetry ingestion pipeline.
    
    For Snowflake: Creates telemetry table, file format, stage, and Snowflake Pipe.
    For DuckDB: Creates telemetry table only (local files loaded via manifest-driven orchestration).
    #}
    {{ log('Provisioning telemetry pipeline...', info=true) }}

    {% set database = target.database %}
    {% set infra_schema = var('infra_schema') %}
    {% set ingest_schema = var('ingest_schema') %}
    {% set telemetry_table = var('telemetry_raw_table') %}
    {% set storage_integration = var('storage_integration_name') %}
    {% set telemetry_url = var('telemetry_blob_url') %}

    {{ create_telemetry_raw_table(database, ingest_schema, telemetry_table) }}

    {% if target.type == 'snowflake' %}
        {% if telemetry_url == '' %}
            {{ exceptions.raise_compiler_error('telemetry_blob_url required for Snowflake provisioning') }}
        {% endif %}

        {% set json_format = 'TELEMETRY_JSON_FORMAT' %}
        {{ create_json_file_format(database, infra_schema, json_format) }}

        {% set stage_name = 'TELEMETRY_STAGE' %}
        {% set pipe_name = 'TELEMETRY_PIPE' %}
        {{ create_telemetry_stage_and_pipe(database, infra_schema, stage_name, storage_integration, telemetry_url, json_format, pipe_name, telemetry_table, ingest_schema) }}

        {{ log('✓ Telemetry pipeline provisioned for Snowflake', info=true) }}
    {% elif target.type == 'duckdb' %}
        {{ log('✓ Telemetry raw table created for DuckDB (files loaded via orchestration)', info=true) }}
    {% else %}
        {{ log('⚠ Unknown adapter type: ' ~ target.type ~ ', skipping telemetry provisioning', info=true) }}
    {% endif %}
{% endmacro %}
