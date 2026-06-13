{% macro create_max_publication_view(database_name, presentation_schema, view_name, presentation_base_view) %}
    {{ return(adapter.dispatch('create_max_publication_view')(database_name, presentation_schema, view_name, presentation_base_view)) }}
{% endmacro %}

{% macro default__create_max_publication_view(database_name, presentation_schema, view_name, presentation_base_view) %}
    {# Generic implementation #}
    {% set sql %}
        create or replace view {{ adapter.quote(presentation_schema) }}.{{ adapter.quote(view_name) }} as
        select *
        from {{ adapter.quote(presentation_schema) }}.{{ adapter.quote(presentation_base_view) }}
        where _PUBLICATION_DATE = (
            select max(_PUBLICATION_DATE)
            from {{ adapter.quote(presentation_schema) }}.{{ adapter.quote(presentation_base_view) }}
        )
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created max publication view ' ~ presentation_schema ~ '.' ~ view_name) }}
{% endmacro %}
