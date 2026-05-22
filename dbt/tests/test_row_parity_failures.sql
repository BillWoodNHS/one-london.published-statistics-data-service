select *
from {{ ref('fct_row_parity') }}
where row_parity_pass = false
