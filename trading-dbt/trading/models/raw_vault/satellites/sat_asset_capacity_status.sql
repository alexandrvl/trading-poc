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
        declared_availability_mw,
        outage_status,
        derating_factor,
        rsrc
    from {{ ref('stg_capacity_status') }}
    where hk_asset is not null
)

{{ satellite_changes(['hk_asset']) }}
