{{ config(materialized='view', enabled=(target.type == 'postgres')) }}

select
    activation_id,
    portfolio_id,
    market_code,
    interval_start,
    interval_end,
    volume_mw,
    price_eur_mwh,
    activation_type,
    {{ hash_key('portfolio_id', 'hk_portfolio') }},
    {{ hash_key('market_code', 'hk_market') }},
    {{ hash_diff([
        'volume_mw', 'price_eur_mwh', 'activation_type', 'interval_end'
    ], 'hashdiff') }},
    interval_start as ldts,
    coalesce(source_system, 'PERIOTHEUS') as rsrc
from {{ source('raw', 'mfrr_activations') }}
where activation_id is not null
  and interval_start is not null
