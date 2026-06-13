{% macro snowflake__create_csv_file_format(database_name, schema_name, file_format_name) %}
    {% set sql %}
        create file format if not exists {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(file_format_name) }}
        type = csv
        field_delimiter = ','
        skip_header = 1
        parse_header = true
        field_optionally_enclosed_by = '"'
        empty_field_as_null = true
        trim_space = true
    {% endset %}
    {% do run_query(sql) %}
    {{ return('created file format ' ~ schema_name ~ '.' ~ file_format_name) }}
{% endmacro %}
