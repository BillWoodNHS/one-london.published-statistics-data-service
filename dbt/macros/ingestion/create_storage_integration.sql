{% macro create_storage_integration(storage_integration_name, allowed_location, tenant_id) %}
    {{ return(adapter.dispatch('create_storage_integration')(storage_integration_name, allowed_location, tenant_id)) }}
{% endmacro %}

{% macro default__create_storage_integration(storage_integration_name, allowed_location, tenant_id) %}
    {{ return('skipped storage integration for adapter ' ~ target.type) }}
{% endmacro %}
