{% macro snowflake__create_storage_integration(storage_integration_name, allowed_location, tenant_id) %}
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
