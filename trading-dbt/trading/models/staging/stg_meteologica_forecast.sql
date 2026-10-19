{{ config(materialized='view') }}

select
    asset_id,
    forecast_run_ts,
    type_code,
    target_timestamp,
    expected_power_kw,
    wind_speed_m_s,
    ghi_w_m2,
    {{ hash_key('asset_id', 'hk_asset') }},
    {{ hash_diff([
        'expected_power_kw', 'wind_speed_m_s', 'ghi_w_m2'
    ], 'hashdiff') }},
    forecast_run_ts as ldts,
    coalesce(source_system, 'METEOLOGICA') as rsrc
from {{ source('raw', 'meteologica_forecast') }}
where asset_id is not null
  and type_code is not null
  and target_timestamp is not null
  and forecast_run_ts is not null
