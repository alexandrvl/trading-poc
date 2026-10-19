{{ config(materialized='view') }}

select
    portfolio_id,
    market_code,
    interval_start,
    interval_end,
    capacity_revenue_eur,
    energy_revenue_eur,
    penalty_eur,
    {{ hash_key('portfolio_id', 'hk_portfolio') }},
    {{ hash_key('market_code', 'hk_market') }},
    loaded_at as ldts,
    coalesce(source_system, 'PERIOTHEUS') as rsrc
from {{ source('raw', 'balancing_settlement') }}
where portfolio_id is not null
  and market_code is not null
  and interval_start is not null
