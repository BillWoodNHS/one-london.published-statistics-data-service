{% macro create_current_revision_view(database_name, presentation_schema, view_name, max_publication_view) %}
    {{ return(adapter.dispatch('create_current_revision_view')(database_name, presentation_schema, view_name, max_publication_view)) }}
{% endmacro %}

{% macro default__create_current_revision_view(database_name, presentation_schema, view_name, max_publication_view) %}
    {# Generic implementation #}
    {% set sql %}
        create or replace view {{ adapter.quote(presentation_schema) }}.{{ adapter.quote(view_name) }} as
        select *
        from {{ adapter.quote(presentation_schema) }}.{{ adapter.quote(max_publication_view) }}
        qualify row_number() over (partition by _SUBJECT_PERIOD_FROM, _SUBJECT_PERIOD_TO order by _LOADED_AT desc) = 1
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created current revision view ' ~ presentation_schema ~ '.' ~ view_name) }}
{% endmacro %}
