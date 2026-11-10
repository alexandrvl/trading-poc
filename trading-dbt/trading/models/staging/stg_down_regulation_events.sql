{{ config(materialized='view', enabled=(target.type == 'postgres')) }}

select
    event_id,
    asset_id,
    portfolio_id,
    interval_start,
    interval_end,
    commanded_setpoint_kw,
    reason,
    market_code,
    event_ts,
    {{ hash_key('asset_id', 'hk_asset') }},
    {{ hash_key('event_id', 'hk_event') }},
    {{ hash_diff([
        'commanded_setpoint_kw', 'reason', 'market_code', 'interval_start', 'interval_end'
    ], 'hashdiff') }},
    event_ts as ldts,
    coalesce(source_system, 'PERIOTHEUS') as rsrc
from {{ source('raw', 'down_regulation_events') }}
where event_id is not null
  and asset_id is not null
  and interval_start is not null
