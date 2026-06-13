{% macro create_json_file_format(database_name, schema_name, file_format_name) %}
    {{ return(adapter.dispatch('create_json_file_format')(database_name, schema_name, file_format_name)) }}
{% endmacro %}

{% macro default__create_json_file_format(database_name, schema_name, file_format_name) %}
    {{ return('skipped json file format for adapter ' ~ target.type) }}
{% endmacro %}
