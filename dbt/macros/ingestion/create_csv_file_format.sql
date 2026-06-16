{% macro create_csv_file_format(database_name, schema_name, file_format_name) %}
    {{ return(adapter.dispatch('create_csv_file_format')(database_name, schema_name, file_format_name)) }}
{% endmacro %}

{% macro default__create_csv_file_format(database_name, schema_name, file_format_name) %}
    {{ return('skipped csv file format for adapter ' ~ target.type) }}
{% endmacro %}
