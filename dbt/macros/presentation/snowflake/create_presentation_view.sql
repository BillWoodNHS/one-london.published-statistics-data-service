{% macro snowflake__create_presentation_view(database_name, presentation_schema, view_name, raw_schema, raw_table, period_columns) %}
    {% set raw_relation = api.Relation.create(database=database_name, schema=raw_schema, identifier=raw_table) %}
    {% set select_list = one_london_psds.get_screaming_snake_select_list(raw_relation) %}
    {% set sql %}
        create or replace view {{ adapter.quote(database_name) }}.{{ adapter.quote(presentation_schema) }}.{{ adapter.quote(view_name) }} as
        select
            {{ select_list }},
            current_timestamp::timestamp_ntz as _LOADED_AT
        from {{ adapter.quote(database_name) }}.{{ adapter.quote(raw_schema) }}.{{ adapter.quote(raw_table) }}
        where _SUBJECT_PERIOD_FROM is not null
            and _SUBJECT_PERIOD_TO is not null
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created presentation view ' ~ presentation_schema ~ '.' ~ view_name) }}
{% endmacro %}
