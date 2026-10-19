{{ config(materialized='view') }}

select
    portfolio_id,
    market_code,
    interval_start,
    interval_end,
    revenue_eur,
    volume_mwh,
    imbalance_cost_eur,
    clearing_price_eur_mwh,
    {{ hash_key('portfolio_id', 'hk_portfolio') }},
    {{ hash_key('market_code', 'hk_market') }},
    loaded_at as ldts,
    coalesce(source_system, 'PERIOTHEUS') as rsrc
from {{ source('raw', 'portfolio_settlement') }}
where portfolio_id is not null
  and market_code is not null
  and interval_start is not null
