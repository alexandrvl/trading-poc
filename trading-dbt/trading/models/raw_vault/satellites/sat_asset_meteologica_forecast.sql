{{
    config(
        unique_key=['hk_asset', 'ldts', 'type_code', 'target_timestamp'],
        properties={
            "format": "'PARQUET'",
            "partitioning": "ARRAY['day(ldts)']"
        }
    )
}}

-- Multi-active satellite. type_code is the third primary-key component so
-- P10, P50, P90 and the intraday downscale can share one load timestamp.
with source as (
    select
        hk_asset,
        ldts,
        type_code,
        target_timestamp,
        hashdiff,
        asset_id,
        expected_power_kw,
        wind_speed_m_s,
        ghi_w_m2,
        rsrc
    from {{ ref('stg_meteologica_forecast') }}
    where hk_asset is not null
)

{{ satellite_changes(['hk_asset', 'type_code', 'target_timestamp']) }}
