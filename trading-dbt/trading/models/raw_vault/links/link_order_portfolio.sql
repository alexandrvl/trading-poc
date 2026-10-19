{{
    config(
        unique_key='hk_link_order_portfolio'
    )
}}

with deduped as (
    select hk_link_order_portfolio, hk_order, hk_portfolio, ldts, rsrc
    from (
        select
            hk_link_order_portfolio,
            hk_order,
            hk_portfolio,
            ldts,
            rsrc,
            row_number() over (partition by hk_link_order_portfolio order by ldts) as rn
        from {{ ref('stg_trade_orders') }}
        where hk_link_order_portfolio is not null
    )
    where rn = 1
)

select *
from deduped
{{ incremental_hub('hk_link_order_portfolio') }}
