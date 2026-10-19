{{ config(materialized='view') }}

select
    market_code,
    market_name,
    segment,
    product_resolution_min,
    tso,
    currency_code,
    {{ hash_key('market_code', 'hk_market') }},
    {{ hash_diff([
        'market_name', 'segment', 'product_resolution_min', 'tso', 'currency_code'
    ], 'hashdiff') }},
    cast(timestamp '2020-01-01 00:00:00' as timestamp(6)) as ldts,
    coalesce(source_system, 'PERIOTHEUS') as rsrc
from {{ source('raw', 'markets') }}
where market_code is not null
