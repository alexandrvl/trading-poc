{{ config(materialized='view') }}

select
    portfolio_id,
    portfolio_name,
    bidding_zone,
    strategy_module,
    status,
    valid_from,
    {{ hash_key('portfolio_id', 'hk_portfolio') }},
    {{ hash_diff([
        'portfolio_name', 'bidding_zone', 'strategy_module', 'status', 'valid_from'
    ], 'hashdiff') }},
    last_modified as ldts,
    coalesce(source_system, 'PERIOTHEUS') as rsrc
from {{ source('raw', 'portfolios') }}
where portfolio_id is not null
