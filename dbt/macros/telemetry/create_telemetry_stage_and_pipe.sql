{% macro create_telemetry_stage_and_pipe(database_name, infra_schema, stage_name, storage_integration, url, file_format, pipe_name, target_table, target_schema=var('ingest_schema')) %}
    {{ return(adapter.dispatch('create_telemetry_stage_and_pipe')(database_name, infra_schema, stage_name, storage_integration, url, file_format, pipe_name, target_table, target_schema)) }}
{% endmacro %}

{% macro default__create_telemetry_stage_and_pipe(database_name, infra_schema, stage_name, storage_integration, url, file_format, pipe_name, target_table, target_schema) %}
    {{ return('skipped telemetry stage/pipe for adapter ' ~ target.type) }}
{% endmacro %}
