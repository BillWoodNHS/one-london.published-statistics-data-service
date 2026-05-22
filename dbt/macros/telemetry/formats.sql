{% macro create_json_file_format(database_name, schema_name, file_format_name) %}
    {% set sql %}
        create file format if not exists {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(file_format_name) }}
        type = json
        strip_outer_array = false
    {% endset %}
    {% do run_query(sql) %}
    {{ return('created json file format ' ~ schema_name ~ '.' ~ file_format_name) }}
{% endmacro %}
