{{
    config(
        unique_key=['hk_link_portfolio_asset', 'ldts', 'valid_from']
    )
}}

with source as (
    select
        hk_link_portfolio_asset,
        ldts,
        hashdiff,
        hk_portfolio,
        hk_asset,
        portfolio_id,
        asset_id,
        valid_from,
        valid_to,
        membership_share,
        rsrc
    from {{ ref('stg_portfolio_membership') }}
    where hk_link_portfolio_asset is not null
)

{{ satellite_changes(['hk_link_portfolio_asset', 'valid_from']) }}
