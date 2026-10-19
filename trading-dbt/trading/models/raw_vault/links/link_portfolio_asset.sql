{{
    config(
        unique_key='hk_link_portfolio_asset'
    )
}}

with source as (
    select
        hk_link_portfolio_asset,
        hk_portfolio,
        hk_asset,
        ldts,
        rsrc,
        row_number() over (partition by hk_link_portfolio_asset order by ldts) as rn
    from {{ ref('stg_portfolio_membership') }}
    where hk_link_portfolio_asset is not null
),
deduped as (
    select hk_link_portfolio_asset, hk_portfolio, hk_asset, ldts, rsrc
    from source
    where rn = 1
)

select *
from deduped
{{ incremental_hub('hk_link_portfolio_asset') }}
