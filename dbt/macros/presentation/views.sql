{% macro create_presentation_view(raw_database, raw_schema, raw_table, view_schema, view_name) %}
    {% set relation = adapter.get_relation(database=raw_database, schema=raw_schema, identifier=raw_table) %}
    {% if relation is none %}
        {{ exceptions.raise_compiler_error('Raw relation not found: ' ~ raw_database ~ '.' ~ raw_schema ~ '.' ~ raw_table) }}
    {% endif %}

    {% set select_list = one_london_psds.get_screaming_snake_select_list(relation) %}

    {% set sql %}
        create or replace view {{ adapter.quote(raw_database) }}.{{ adapter.quote(view_schema) }}.{{ adapter.quote(view_name) }} as
        select
            {{ select_list }}
        from {{ relation }}
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created view ' ~ view_schema ~ '.' ~ view_name) }}
{% endmacro %}


{% macro create_max_publication_view(database_name, schema_name, source_view, output_view, reporting_period_columns) %}
    {% set key_columns = reporting_period_columns | join(', ') %}
    {% set sql %}
        create or replace view {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(output_view) }} as
        select
            {{ key_columns }},
            max(_PUBLICATION_DATE) as MAX_PUBLICATION_DATE
        from {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(source_view) }}
        group by {{ key_columns }}
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created view ' ~ schema_name ~ '.' ~ output_view) }}
{% endmacro %}


{% macro create_current_revision_view(database_name, schema_name, source_view, max_pub_view, output_view, reporting_period_columns) %}
    {% set join_parts = [] %}
    {% for col in reporting_period_columns %}
        {% do join_parts.append('src.' ~ adapter.quote(col) ~ ' = mx.' ~ adapter.quote(col)) %}
    {% endfor %}

    {% set join_predicate = join_parts | join(' and ') %}
    {% set sql %}
        create or replace view {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(output_view) }} as
        select src.*
        from {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(source_view) }} src
        join {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(max_pub_view) }} mx
          on {{ join_predicate }}
         and src._PUBLICATION_DATE = mx.MAX_PUBLICATION_DATE
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created view ' ~ schema_name ~ '.' ~ output_view) }}
{% endmacro %}
