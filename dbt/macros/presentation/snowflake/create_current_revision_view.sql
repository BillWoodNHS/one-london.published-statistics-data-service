{% macro snowflake__create_current_revision_view(database_name, presentation_schema, view_name, presentation_base_view, max_publication_view, reporting_columns, period_coverage) %}
    {% if reporting_columns and reporting_columns | length > 0 %}
        {% set period_cols = reporting_columns %}
    {% else %}
        {% set period_cols = ['_SUBJECT_PERIOD_FROM', '_SUBJECT_PERIOD_TO'] %}
    {% endif %}

    {% set sql %}
        create or replace view {{ adapter.quote(database_name) }}.{{ adapter.quote(presentation_schema) }}.{{ adapter.quote(view_name) }} as
        select a.*
        from {{ adapter.quote(database_name) }}.{{ adapter.quote(presentation_schema) }}.{{ adapter.quote(presentation_base_view) }} a
        join {{ adapter.quote(database_name) }}.{{ adapter.quote(presentation_schema) }}.{{ adapter.quote(max_publication_view) }} b
          on a._SOURCE_FILE_NAME = b._SOURCE_FILE_NAME
         and a._SOURCE_FILE_PATH = b._SOURCE_FILE_PATH
         and a._INGESTED_AT = b._INGESTED_AT
        {% for col in period_cols %}
         and a.{{ col }} = b.{{ col }}
        {% endfor %}
        where b._PUBLICATION_RANK = 1
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created current revision view ' ~ presentation_schema ~ '.' ~ view_name) }}
{% endmacro %}
