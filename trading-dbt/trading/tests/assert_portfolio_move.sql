select
    asset_id,
    portfolio_id,
    interval_start
from {{ ref('mart_asset_internal_billing') }}
where asset_id = 'WT-EE-N-12'
  and portfolio_id <> 'Wind_EE_North'
