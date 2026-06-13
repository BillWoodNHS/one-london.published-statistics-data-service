{#
These macros have been moved to their own files with adapter dispatch structure:
- create_csv_file_format.sql / snowflake/create_csv_file_format.sql
- create_ingest_table.sql / snowflake/create_ingest_table.sql
- create_raw_table.sql (deprecated, use create_ingest_table)
- create_raw_dedup_view.sql (generic macro)

See adapter-specific implementations in:
- dbt/macros/ingestion/snowflake/
- dbt/macros/ingestion/duckdb/
#}
