{{
    config(
        unique_key='hk_order'
    )
}}

with source as (
    select hk_order, order_id, ldts, rsrc
    from {{ ref('stg_trade_orders') }}
    where hk_order is not null
      and order_id is not null
),
deduped as (
    select hk_order, order_id, ldts, rsrc
    from (
        select
            hk_order,
            order_id,
            ldts,
            rsrc,
            row_number() over (partition by hk_order order by ldts) as rn
        from source
    ) ranked
    where rn = 1
)

select *
from deduped
{{ incremental_hub('hk_order') }}
