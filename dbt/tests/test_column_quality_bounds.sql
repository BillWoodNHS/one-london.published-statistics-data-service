select *
from {{ ref('fct_column_quality_profile') }}
where (
    null_pct is not null
    and (null_pct < 0 or null_pct > 1)
)
or (
    row_count is not null
    and distinct_value_count is not null
    and distinct_value_count > row_count
)
