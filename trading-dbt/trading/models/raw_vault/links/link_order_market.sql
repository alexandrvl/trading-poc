{{
    config(
        unique_key='hk_link_order_market'
    )
}}

with deduped as (
    select hk_link_order_market, hk_order, hk_market, ldts, rsrc
    from (
        select
            hk_link_order_market,
            hk_order,
            hk_market,
            ldts,
            rsrc,
            row_number() over (partition by hk_link_order_market order by ldts) as rn
        from {{ ref('stg_trade_orders') }}
        where hk_link_order_market is not null
    )
    where rn = 1
)

select *
from deduped
{{ incremental_hub('hk_link_order_market') }}
