{{ config(materialized='view') }}

select
    asset_id,
    status_ts,
    declared_availability_mw,
    outage_status,
    derating_factor,
    {{ hash_key('asset_id', 'hk_asset') }},
    {{ hash_diff([
        'declared_availability_mw', 'outage_status', 'derating_factor'
    ], 'hashdiff') }},
    status_ts as ldts,
    coalesce(source_system, 'EMSYS_VPP') as rsrc
from {{ source('raw', 'capacity_status') }}
where asset_id is not null
  and status_ts is not null
