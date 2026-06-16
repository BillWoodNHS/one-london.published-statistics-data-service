{% macro snowflake__create_max_publication_view(database_name, presentation_schema, view_name, presentation_base_view, reporting_columns, period_coverage) %}
    {% if reporting_columns and reporting_columns | length > 0 %}
        {% set period_cols = reporting_columns %}
    {% else %}
        {% set period_cols = ['_SUBJECT_PERIOD_FROM', '_SUBJECT_PERIOD_TO'] %}
    {% endif %}
    {% set period_partition = period_cols | join(', ') %}

    {% set sql %}
        create or replace view {{ adapter.quote(database_name) }}.{{ adapter.quote(presentation_schema) }}.{{ adapter.quote(view_name) }} as
        with file_coverage as (
            select
                *,
                max(_SUBJECT_PERIOD_TO) over (
                    partition by _SOURCE_FILE_NAME, _SOURCE_FILE_PATH, _INGESTED_AT
                ) as _FILE_MAX_SUBJECT_TO
            from {{ adapter.quote(database_name) }}.{{ adapter.quote(presentation_schema) }}.{{ adapter.quote(presentation_base_view) }}
        )
        select * exclude (_FILE_MAX_SUBJECT_TO)
        from file_coverage
        qualify row_number() over (
            partition by {{ period_partition }}
            order by _FILE_MAX_SUBJECT_TO desc, _PUBLICATION_DATE desc nulls last, _INGESTED_AT desc
        ) = 1
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created max publication view ' ~ presentation_schema ~ '.' ~ view_name) }}
{% endmacro %}
