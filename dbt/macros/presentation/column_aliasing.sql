{% macro to_screaming_snake(identifier) -%}
    {{ return(adapter.dispatch('to_screaming_snake', 'one_london_psds')(identifier)) }}
{%- endmacro %}

{% macro default__to_screaming_snake(identifier) -%}
    {% set value = identifier %}
    {% set value = modules.re.sub('([A-Z]+)([A-Z][a-z])', '\\1_\\2', value) %}
    {% set value = modules.re.sub('([a-z0-9])([A-Z])', '\\1_\\2', value) %}
    {% set value = modules.re.sub('[^A-Za-z0-9]+', '_', value) %}
    {% set value = modules.re.sub('_+', '_', value) %}
    {% set value = value.strip('_') %}
    {{ return(value | upper) }}
{%- endmacro %}

{% macro get_relation_column_names(database_name, schema_name, table_name) -%}
    {{ return(adapter.dispatch('get_relation_column_names', 'one_london_psds')(database_name, schema_name, table_name)) }}
{%- endmacro %}

{% macro default__get_relation_column_names(database_name, schema_name, table_name) -%}
    {#
    Looks up column names via a plain run_query() against information_schema rather than
    adapter.get_relation()/adapter.get_columns_in_relation(): those introspection calls were
    observed to open a transaction that never gets committed when used from inside a
    run_query()-driven provisioning macro (e.g. provision_presentation_from_manifest), causing
    every view created afterwards in the same macro to be silently rolled back instead of
    persisted. run_query() itself doesn't have this problem, so we use it for the lookup too.
    #}
    {% set columns_sql %}
        select column_name
        from information_schema.columns
        where lower(table_schema) = lower('{{ schema_name }}')
          and lower(table_name) = lower('{{ table_name }}')
        order by ordinal_position
    {% endset %}
    {% set results = run_query(columns_sql) %}
    {% set column_names = [] %}
    {% if results is not none %}
        {% for row in results.rows %}
            {% do column_names.append(row[0]) %}
        {% endfor %}
    {% endif %}
    {{ return(column_names) }}
{%- endmacro %}

{% macro get_screaming_snake_select_list(database_name, schema_name, table_name) -%}
    {% set column_names = one_london_psds.get_relation_column_names(database_name, schema_name, table_name) %}
    {{ return(one_london_psds.get_screaming_snake_select_list_from_names(column_names)) }}
{%- endmacro %}

{% macro get_screaming_snake_select_list_from_names(column_names) -%}
    {% set metadata_columns = var('metadata_columns', []) %}
    {% set select_items = [] %}
    {% set emitted = [] %}

    {% for original in column_names %}
        {% if original in metadata_columns %}
            {% set alias = original %}
        {% else %}
            {% set alias = one_london_psds.to_screaming_snake(original) %}
        {% endif %}

        {% if alias in emitted %}
            {% set alias = alias ~ '_' ~ loop.index %}
        {% endif %}

        {% do emitted.append(alias) %}
        {% do select_items.append(adapter.quote(original) ~ ' as ' ~ adapter.quote(alias)) %}
    {% endfor %}

    {{ return(select_items | join(',\n    ')) }}
{%- endmacro %}

{% macro emit_alias_select_sql(column_names) -%}
    {% set sql = one_london_psds.get_screaming_snake_select_list_from_names(column_names) %}
    {{ log('__ALIAS_SELECT_SQL__' ~ sql, info=True) }}
    {{ return(sql) }}
{%- endmacro %}

{% macro test_create_presentation_view_with_aliasing(raw_schema, raw_table, view_name, column_names) -%}
    {#
    Test-support macro: builds a throwaway RAW table from column_names, runs it through
    create_presentation_view, and emits the resulting PRESENTATION view's column names.
    Used by tests/test_duckdb_presentation_view_aliasing.py to verify create_presentation_view
    wires in screaming-snake-case column aliasing end-to-end (not just the alias-list macro).
    #}
    {% set database_name = target.database %}

    {% do run_query('create schema if not exists ' ~ adapter.quote(raw_schema)) %}

    {% set column_defs = [] %}
    {% for col in column_names %}
        {% do column_defs.append(adapter.quote(col) ~ ' varchar') %}
    {% endfor %}
    {% do run_query(
        'create or replace table ' ~ adapter.quote(raw_schema) ~ '.' ~ adapter.quote(raw_table) ~
        ' (' ~ (column_defs | join(', ')) ~ ')'
    ) %}

    {% set insert_values = [] %}
    {% for col in column_names %}
        {% if col in ['_SUBJECT_PERIOD_FROM', '_SUBJECT_PERIOD_TO'] %}
            {% do insert_values.append("'2026-01-01'") %}
        {% else %}
            {% do insert_values.append("'x'") %}
        {% endif %}
    {% endfor %}
    {% do run_query(
        'insert into ' ~ adapter.quote(raw_schema) ~ '.' ~ adapter.quote(raw_table) ~
        ' values (' ~ (insert_values | join(', ')) ~ ')'
    ) %}

    {% do one_london_psds.create_presentation_view(database_name, raw_schema, view_name, raw_schema, raw_table, []) %}

    {% set presentation_columns = one_london_psds.get_relation_column_names(database_name, raw_schema, view_name) %}
    {{ log('__PRESENTATION_VIEW_COLUMNS__' ~ (presentation_columns | join(',')), info=True) }}
    {{ return(presentation_columns) }}
{%- endmacro %}
