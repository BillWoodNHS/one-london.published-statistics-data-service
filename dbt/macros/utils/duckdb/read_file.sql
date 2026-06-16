{% macro duckdb__read_file(path) %}
    {% set normalized_path = path | replace('\\', '/') | replace("'", "''") %}
    {% set sql %}
        select content from read_text('{{ normalized_path }}')
    {% endset %}
    {% set result = run_query(sql) %}
    {% if result is none or (result.rows | length) == 0 %}
        {{ return(none) }}
    {% endif %}
    {{ return(result.rows[0][0]) }}
{% endmacro %}
