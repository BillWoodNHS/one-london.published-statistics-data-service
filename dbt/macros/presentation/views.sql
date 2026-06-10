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
    {% if reporting_period_columns | length == 0 %}
        {{ return('skipped view ' ~ schema_name ~ '.' ~ output_view ~ ' (no reporting_period_columns configured)') }}
    {% endif %}

    {% set key_columns = reporting_period_columns | join(', ') %}
    {% set sql %}
        create or replace view {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(output_view) }} as
        with ranked as (
            select
                {{ key_columns }},
                _PUBLICATION_DATE,
                _SUBJECT_PERIOD_TO,
                _DOWNLOADED_AT,
                _INGESTED_AT,
                row_number() over (
                    partition by {{ key_columns }}
                    order by
                        case when _PUBLICATION_DATE = '' then 0 else 1 end desc,
                        _PUBLICATION_DATE desc,
                        case when _SUBJECT_PERIOD_TO = '' then 0 else 1 end desc,
                        _SUBJECT_PERIOD_TO desc,
                        _DOWNLOADED_AT desc,
                        _INGESTED_AT desc,
                        _SOURCE_FILE_PATH desc
                ) as _revision_rank
            from {{ adapter.quote(database_name) }}.{{ adapter.quote(schema_name) }}.{{ adapter.quote(source_view) }}
        )
        select
            {{ key_columns }},
            _PUBLICATION_DATE as MAX_PUBLICATION_DATE,
            _SUBJECT_PERIOD_TO as MAX_SUBJECT_PERIOD_TO,
            _DOWNLOADED_AT as MAX_DOWNLOADED_AT,
            _INGESTED_AT as MAX_INGESTED_AT,
            _SOURCE_FILE_PATH as MAX_SOURCE_FILE_PATH
        from ranked
        where _revision_rank = 1
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created view ' ~ schema_name ~ '.' ~ output_view) }}
{% endmacro %}


{% macro create_current_revision_view(database_name, schema_name, source_view, max_pub_view, output_view, reporting_period_columns) %}
    {% if reporting_period_columns | length == 0 %}
        {{ return('skipped view ' ~ schema_name ~ '.' ~ output_view ~ ' (no reporting_period_columns configured)') }}
    {% endif %}

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
                 and src._SUBJECT_PERIOD_TO = mx.MAX_SUBJECT_PERIOD_TO
                 and src._DOWNLOADED_AT = mx.MAX_DOWNLOADED_AT
                 and src._INGESTED_AT = mx.MAX_INGESTED_AT
                 and src._SOURCE_FILE_PATH = mx.MAX_SOURCE_FILE_PATH
    {% endset %}

    {% do run_query(sql) %}
    {{ return('created view ' ~ schema_name ~ '.' ~ output_view) }}
{% endmacro %}
