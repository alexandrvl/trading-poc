{{
    config(
        unique_key=['hk_order', 'ldts']
    )
}}

with source as (
    select
        hk_order,
        ldts,
        hashdiff,
        order_id,
        price_eur,
        volume_mw,
        delivery_start,
        delivery_end,
        order_type,
        direction,
        order_status,
        rsrc
    from {{ ref('stg_trade_orders') }}
    where hk_order is not null
)

{{ satellite_changes(['hk_order']) }}
