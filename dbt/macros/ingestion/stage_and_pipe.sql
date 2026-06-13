{#
These macros have been refactored to use adapter dispatch pattern.
See individual macro files:
- create_stage_and_pipe.sql / snowflake/create_stage_and_pipe.sql
- provision_target_pipeline.sql
- provision_series_from_manifest.sql

Adapter-specific implementations in:
- dbt/macros/ingestion/snowflake/
- dbt/macros/ingestion/duckdb/
#}
