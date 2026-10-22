{{
    config(
        unique_key='hk_portfolio'
    )
}}

with source as (
    select hk_portfolio, portfolio_id, ldts, rsrc from {{ ref('stg_portfolios') }}
    union all
    select hk_portfolio, portfolio_id, ldts, rsrc from {{ ref('stg_portfolio_membership') }}
    union all
    select hk_portfolio, portfolio_id, ldts, rsrc from {{ ref('stg_trade_orders') }}
    union all
    select hk_portfolio, portfolio_id, ldts, rsrc from {{ ref('stg_portfolio_settlement') }}
    union all
    select hk_portfolio, portfolio_id, ldts, rsrc from {{ ref('stg_balancing_settlement') }}
),
deduped as (
    select hk_portfolio, portfolio_id, ldts, rsrc
    from (
        select
            hk_portfolio,
            portfolio_id,
            ldts,
            rsrc,
            row_number() over (partition by hk_portfolio order by ldts) as rn
        from source
        where hk_portfolio is not null
          and portfolio_id is not null
    ) ranked
    where rn = 1
)

select *
from deduped
{{ incremental_hub('hk_portfolio') }}
