{% macro snowflake__create_current_revision_view(database_name, presentation_schema, view_name, max_publication_view, reporting_columns, period_coverage) %}
    {% if reporting_columns and reporting_columns | length > 0 %}
        {% set period_cols = reporting_columns %}
    {% else %}
        {% set period_cols = ['_SUBJECT_PERIOD_FROM', '_SUBJECT_PERIOD_TO'] %}
    {% endif %}
    {% set period_partition = period_cols | join(', ') %}

    {% set sql %}
        create or replace view {{ adapter.quote(database_name) }}.{{ adapter.quote(presentation_schema) }}.{{ adapter.quote(view_name) }} as
        select *
        from {{ adapter.quote(database_name) }}.{{ adapter.quote(presentation_schema) }}.{{ adapter.quote(max_publication_view) }}
        qualify row_number() over (partition by {{ period_partition }} order by _LOADED_AT desc) = 1
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created current revision view ' ~ presentation_schema ~ '.' ~ view_name) }}
{% endmacro %}
