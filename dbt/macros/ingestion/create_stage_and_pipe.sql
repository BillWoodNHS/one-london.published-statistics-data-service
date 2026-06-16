{% macro create_stage_and_pipe(database_name, schema_name, stage_name, storage_integration, url, file_format, pipe_name, target_table, target_schema, pattern='.*\\.csv') %}
    {{ return(adapter.dispatch('create_stage_and_pipe')(database_name, schema_name, stage_name, storage_integration, url, file_format, pipe_name, target_table, target_schema, pattern)) }}
{% endmacro %}

{% macro default__create_stage_and_pipe(database_name, schema_name, stage_name, storage_integration, url, file_format, pipe_name, target_table, target_schema, pattern='.*\\.csv') %}
    {{ return('skipped stage and pipe for adapter ' ~ target.type) }}
{% endmacro %}
