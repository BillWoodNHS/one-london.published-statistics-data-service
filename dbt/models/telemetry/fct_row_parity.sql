with normalize_events as (
    select
        LOAD_ID as load_id,
        SERIES_ID as series_id,
        SUB_DATASET_ID as sub_dataset_id,
        SOURCE_URL as source_url,
        FILE_NAME as file_name,
        max(NORMALIZED_ROW_COUNT) as normalized_row_count,
        max(EVENT_TIMESTAMP_UTC) as normalized_at
    from {{ ref('stg_function_app_events') }}
    where STAGE = 'UPLOAD'
      and STATUS = 'SUCCEEDED'
      and LOAD_ID is not null
    group by LOAD_ID, SERIES_ID, SUB_DATASET_ID, SOURCE_URL, FILE_NAME
),
loaded as (
    select
        load_id,
        sum(loaded_row_count) as loaded_row_count
    from {{ ref('int_loaded_row_counts') }}
    group by load_id
)
select
    n.load_id,
    n.series_id,
    n.sub_dataset_id,
    n.source_url,
    n.file_name,
    n.normalized_row_count,
    l.loaded_row_count,
    case
        when n.normalized_row_count is null or l.loaded_row_count is null then null
        when n.normalized_row_count = l.loaded_row_count then true
        else false
    end as row_parity_pass,
    n.normalized_at
from normalize_events n
left join loaded l on l.load_id = n.load_id
