{{
    config(
        unique_key='hk_asset'
    )
}}

with source as (
    select hk_asset, asset_id, ldts, rsrc from {{ ref('stg_assets') }}
    union all
    select hk_asset, asset_id, ldts, rsrc from {{ ref('stg_emsys_telemetry') }}
    union all
    select hk_asset, asset_id, ldts, rsrc from {{ ref('stg_capacity_status') }}
    union all
    select hk_asset, asset_id, ldts, rsrc from {{ ref('stg_meteologica_forecast') }}
    union all
    select hk_asset, asset_id, ldts, rsrc from {{ ref('stg_portfolio_membership') }}
),
deduped as (
    select hk_asset, asset_id, ldts, rsrc
    from (
        select
            hk_asset,
            asset_id,
            ldts,
            rsrc,
            row_number() over (partition by hk_asset order by ldts) as rn
        from source
        where hk_asset is not null
          and asset_id is not null
    ) ranked
    where rn = 1
)

select *
from deduped
{{ incremental_hub('hk_asset') }}
