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

{% macro get_screaming_snake_select_list(relation) -%}
    {% set columns = adapter.get_columns_in_relation(relation) %}
    {{ return(one_london_psds.get_screaming_snake_select_list_from_names(columns | map(attribute='name') | list)) }}
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
