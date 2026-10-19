{{ config(materialized='view') }}

select
    portfolio_id,
    asset_id,
    valid_from,
    valid_to,
    membership_share,
    {{ hash_key('portfolio_id', 'hk_portfolio') }},
    {{ hash_key('asset_id', 'hk_asset') }},
    {{ hash_key(['portfolio_id', 'asset_id'], 'hk_link_portfolio_asset') }},
    {{ hash_diff(['valid_from', 'valid_to', 'membership_share'], 'hashdiff') }},
    last_modified as ldts,
    coalesce(source_system, 'PERIOTHEUS') as rsrc
from {{ source('raw', 'portfolio_membership') }}
where portfolio_id is not null
  and asset_id is not null
  and valid_from is not null
