{{ config(materialized='view', enabled=(target.type == 'postgres')) }}

select
    activation_id,
    portfolio_id,
    asset_id,
    event_ts,
    setpoint_kw,
    direction,
    price_eur_mwh,
    {{ hash_key('portfolio_id', 'hk_portfolio') }},
    {{ hash_key('asset_id', 'hk_asset') }},
    event_ts as ldts,
    coalesce(source_system, 'PERIOTHEUS') as rsrc
from {{ source('raw', 'afrr_activations') }}
where activation_id is not null
  and event_ts is not null
