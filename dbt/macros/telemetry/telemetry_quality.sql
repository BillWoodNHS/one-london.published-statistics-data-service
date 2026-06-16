{% macro union_raw_load_counts(database_name=target.database, raw_schema=var('raw_schema')) %}
    {% if not execute %}
        {{ return("select null::varchar as raw_table_name, null::varchar as load_id, null::number as loaded_row_count where 1=0") }}
    {% endif %}

    {% set sql %}
        {% if target.type == 'duckdb' %}
            select table_name
            from information_schema.tables
            where table_schema = '{{ raw_schema }}'
              and table_name like 'RAW_%'
              and table_name <> 'RAW_FUNCTION_APP_EVENTS'
            order by table_name
        {% else %}
            select table_name
            from {{ adapter.quote(database_name) }}.information_schema.tables
            where table_schema = upper('{{ raw_schema }}')
              and table_name like 'RAW_%'
              and table_name <> 'RAW_FUNCTION_APP_EVENTS'
            order by table_name
        {% endif %}
    {% endset %}

    {% set results = run_query(sql) %}
    {% if results is none or (results.rows | length) == 0 %}
        {{ return("select null::varchar as raw_table_name, null::varchar as load_id, null::number as loaded_row_count where 1=0") }}
    {% endif %}

    {% set selects = [] %}
    {% for row in results.rows %}
        {% set table_name = row[0] %}
        {% set select_sql %}
            select
                '{{ table_name }}' as raw_table_name,
                _LOAD_ID as load_id,
                count(*) as loaded_row_count
            from {{ adapter.quote(database_name) }}.{{ adapter.quote(raw_schema) }}.{{ adapter.quote(table_name) }}
            where _LOAD_ID is not null
            group by _LOAD_ID
        {% endset %}
        {% do selects.append(select_sql) %}
    {% endfor %}

    {{ return(selects | join(' union all ')) }}
{% endmacro %}


{% macro profile_raw_columns(database_name=target.database, raw_schema=var('raw_schema'), metadata_columns=var('metadata_columns')) %}
    {% if not execute %}
        {{ return("select null::varchar as raw_table_name, null::varchar as column_name, null::number as row_count, null::number as null_count, null::float as null_pct, null::number as distinct_value_count where 1=0") }}
    {% endif %}

    {% set sql %}
        {% if target.type == 'duckdb' %}
            select table_name
            from information_schema.tables
            where table_schema = '{{ raw_schema }}'
              and table_name like 'RAW_%'
              and table_name <> 'RAW_FUNCTION_APP_EVENTS'
            order by table_name
        {% else %}
            select table_name
            from {{ adapter.quote(database_name) }}.information_schema.tables
            where table_schema = upper('{{ raw_schema }}')
              and table_name like 'RAW_%'
              and table_name <> 'RAW_FUNCTION_APP_EVENTS'
            order by table_name
        {% endif %}
    {% endset %}

    {% set table_results = run_query(sql) %}
    {% if table_results is none or (table_results.rows | length) == 0 %}
        {{ return("select null::varchar as raw_table_name, null::varchar as column_name, null::number as row_count, null::number as null_count, null::float as null_pct, null::number as distinct_value_count where 1=0") }}
    {% endif %}

    {% set profile_queries = [] %}
    {% for table_row in table_results.rows %}
        {% set table_name = table_row[0] %}
        {% set relation = adapter.get_relation(database=database_name, schema=raw_schema, identifier=table_name) %}
        {% if relation is none %}
            {% continue %}
        {% endif %}

        {% set columns = adapter.get_columns_in_relation(relation) %}
        {% for col in columns %}
            {% set col_name = col.name %}
            {% if col_name | upper in metadata_columns %}
                {% continue %}
            {% endif %}

            {% set profile_sql %}
                select
                    '{{ table_name }}' as raw_table_name,
                    '{{ col_name }}' as column_name,
                    count(*) as row_count,
                    sum(case when {{ adapter.quote(col_name) }} is null then 1 else 0 end) as null_count,
                    case when count(*) = 0 then null
                         else (sum(case when {{ adapter.quote(col_name) }} is null then 1 else 0 end) * 1.0) / count(*) end as null_pct,
                    count(distinct {{ adapter.quote(col_name) }}) as distinct_value_count
                from {{ adapter.quote(database_name) }}.{{ adapter.quote(raw_schema) }}.{{ adapter.quote(table_name) }}
            {% endset %}
            {% do profile_queries.append(profile_sql) %}
        {% endfor %}
    {% endfor %}

    {% if profile_queries | length == 0 %}
        {{ return("select null::varchar as raw_table_name, null::varchar as column_name, null::number as row_count, null::number as null_count, null::float as null_pct, null::number as distinct_value_count where 1=0") }}
    {% endif %}

    {{ return(profile_queries | join(' union all ')) }}
{% endmacro %}
