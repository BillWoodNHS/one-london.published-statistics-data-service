{% macro create_presentation_view(database_name, presentation_schema, view_name, raw_schema, raw_table, period_columns) %}
    {{ return(adapter.dispatch('create_presentation_view')(database_name, presentation_schema, view_name, raw_schema, raw_table, period_columns)) }}
{% endmacro %}

{% macro default__create_presentation_view(database_name, presentation_schema, view_name, raw_schema, raw_table, period_columns) %}
    {# Generic implementation for DuckDB #}
    {% set sql %}
        create or replace view {{ adapter.quote(presentation_schema) }}.{{ adapter.quote(view_name) }} as
        select
            *,
            current_timestamp() as _LOADED_AT
        from {{ adapter.quote(raw_schema) }}.{{ adapter.quote(raw_table) }}
        where _SUBJECT_PERIOD_FROM is not null
            and _SUBJECT_PERIOD_TO is not null
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created presentation view ' ~ presentation_schema ~ '.' ~ view_name) }}
{% endmacro %}
