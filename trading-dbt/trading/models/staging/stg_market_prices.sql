{{ config(materialized='view') }}

select
    market_code,
    interval_start,
    interval_end,
    clearing_price_eur_mwh,
    {{ hash_key('market_code', 'hk_market') }},
    loaded_at as ldts,
    coalesce(source_system, 'PERIOTHEUS') as rsrc
from {{ source('raw', 'market_prices') }}
where market_code is not null
  and interval_start is not null
