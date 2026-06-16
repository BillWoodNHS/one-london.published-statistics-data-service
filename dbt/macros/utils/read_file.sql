{% macro read_file(path) %}
    {{ return(adapter.dispatch('read_file')(path)) }}
{% endmacro %}

{% macro default__read_file(path) %}
    {{ exceptions.raise_compiler_error('read_file is not supported for adapter ' ~ target.type ~ ' (path: ' ~ path ~ ')') }}
{% endmacro %}
