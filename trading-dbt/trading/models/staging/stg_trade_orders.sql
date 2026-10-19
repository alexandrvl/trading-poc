{{ config(materialized='view') }}

select
    order_id,
    portfolio_id,
    market_code,
    price_eur,
    volume_mw,
    delivery_start,
    delivery_end,
    order_type,
    direction,
    order_status,
    {{ hash_key('order_id', 'hk_order') }},
    {{ hash_key('portfolio_id', 'hk_portfolio') }},
    {{ hash_key('market_code', 'hk_market') }},
    {{ hash_key(['order_id', 'portfolio_id'], 'hk_link_order_portfolio') }},
    {{ hash_key(['order_id', 'market_code'], 'hk_link_order_market') }},
    {{ hash_diff([
        'price_eur', 'volume_mw', 'delivery_start', 'delivery_end',
        'order_type', 'direction', 'order_status'
    ], 'hashdiff') }},
    trade_ts as ldts,
    coalesce(source_system, 'PERIOTHEUS') as rsrc
from {{ source('raw', 'trade_orders') }}
where order_id is not null
