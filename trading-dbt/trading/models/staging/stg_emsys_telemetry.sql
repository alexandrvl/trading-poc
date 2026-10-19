{{ config(materialized='view') }}

select
    telemetry_id,
    asset_id,
    event_ts,
    active_power_kw,
    reactive_power_kvar,
    turbine_status,
    setpoint_limit_kw,
    control_mode,
    {{ hash_key('asset_id', 'hk_asset') }},
    {{ hash_diff([
        'active_power_kw', 'reactive_power_kvar', 'turbine_status',
        'setpoint_limit_kw', 'control_mode', 'event_ts'
    ], 'hashdiff') }},
    ingested_at as ldts,
    coalesce(source_system, 'EMSYS_VPP') as rsrc
from {{ source('raw', 'emsys_telemetry') }}
where asset_id is not null
  and event_ts is not null
  and ingested_at is not null
