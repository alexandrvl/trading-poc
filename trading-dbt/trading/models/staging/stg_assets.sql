{{ config(materialized='view') }}

select
    asset_id,
    asset_name,
    technology,
    nominal_power_kw,
    latitude,
    longitude,
    zone_code,
    turbine_model,
    commissioning_date,
    {{ hash_key('asset_id', 'hk_asset') }},
    {{ hash_diff([
        'asset_name', 'technology', 'nominal_power_kw', 'latitude', 'longitude',
        'zone_code', 'turbine_model', 'commissioning_date'
    ], 'hashdiff') }},
    last_modified as ldts,
    coalesce(source_system, 'EMSYS_VPP') as rsrc
from {{ source('raw', 'assets') }}
where asset_id is not null
