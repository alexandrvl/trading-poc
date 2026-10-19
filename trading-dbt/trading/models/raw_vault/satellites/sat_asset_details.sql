{{
    config(
        unique_key=['hk_asset', 'ldts']
    )
}}

with source as (
    select
        hk_asset,
        ldts,
        hashdiff,
        asset_id,
        asset_name,
        technology,
        nominal_power_kw,
        latitude,
        longitude,
        zone_code,
        turbine_model,
        commissioning_date,
        rsrc
    from {{ ref('stg_assets') }}
    where hk_asset is not null
)

{{ satellite_changes(['hk_asset']) }}
