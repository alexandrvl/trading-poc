{{
    config(
        unique_key=['hk_portfolio', 'ldts']
    )
}}

with source as (
    select
        hk_portfolio,
        ldts,
        hashdiff,
        portfolio_id,
        portfolio_name,
        bidding_zone,
        strategy_module,
        status,
        valid_from,
        rsrc
    from {{ ref('stg_portfolios') }}
    where hk_portfolio is not null
)

{{ satellite_changes(['hk_portfolio']) }}
