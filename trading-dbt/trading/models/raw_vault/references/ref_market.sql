select
    market_code,
    market_name,
    segment,
    product_resolution_min,
    tso,
    currency_code
from {{ ref('stg_markets') }}
