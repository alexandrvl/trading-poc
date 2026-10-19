{{
    config(
        unique_key='hk_market'
    )
}}

with source as (
    select hk_market, market_code, ldts, rsrc from {{ ref('stg_markets') }}
    union all
    select hk_market, market_code, ldts, rsrc from {{ ref('stg_trade_orders') }}
    union all
    select hk_market, market_code, ldts, rsrc from {{ ref('stg_portfolio_settlement') }}
    union all
    select hk_market, market_code, ldts, rsrc from {{ ref('stg_balancing_settlement') }}
    union all
    select hk_market, market_code, ldts, rsrc from {{ ref('stg_market_prices') }}
),
deduped as (
    select hk_market, market_code, ldts, rsrc
    from (
        select
            hk_market,
            market_code,
            ldts,
            rsrc,
            row_number() over (partition by hk_market order by ldts) as rn
        from source
        where hk_market is not null
          and market_code is not null
    )
    where rn = 1
)

select *
from deduped
{{ incremental_hub('hk_market') }}
