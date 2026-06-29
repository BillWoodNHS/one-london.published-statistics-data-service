{% macro snowflake__get_relation_column_names(database_name, schema_name, table_name) -%}
    {% set columns_sql %}
        select column_name
        from {{ adapter.quote(database_name) }}.information_schema.columns
        where table_schema = upper('{{ schema_name }}')
          and table_name = upper('{{ table_name }}')
        order by ordinal_position
    {% endset %}
    {% set results = run_query(columns_sql) %}
    {% set column_names = [] %}
    {% if results is not none %}
        {% for row in results.rows %}
            {% do column_names.append(row[0]) %}
        {% endfor %}
    {% endif %}
    {{ return(column_names) }}
{%- endmacro %}
