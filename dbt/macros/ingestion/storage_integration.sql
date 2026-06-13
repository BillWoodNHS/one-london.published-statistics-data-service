{% macro normalize_identifier(value) %}
    {# Utility macro to normalize dataset identifiers for use in SQL objects #}
    {% set cleaned = value | replace('-', '_') | replace(' ', '_') | replace('/', '_') %}
    {{ return(cleaned | upper) }}
{% endmacro %}

{# Dispatcher macros are now in their own files: create_storage_integration.sql #}
