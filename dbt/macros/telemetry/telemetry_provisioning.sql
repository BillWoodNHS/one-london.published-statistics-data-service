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
