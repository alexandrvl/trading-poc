-- 12:00-12:15 Wind_EE_North is short because WT-EE-N-02 misses its P50.
-- WT-EE-N-12 is long and must not share that charge.
select
    asset_id,
    imbalance_cost_eur
from {{ ref('bv_imbalance_attribution') }}
where portfolio_id = 'Wind_EE_North'
  and interval_start = timestamp '2026-06-01 12:00:00'
  and (
      (asset_id = 'WT-EE-N-02' and imbalance_cost_eur <= 0.01)
      or (asset_id <> 'WT-EE-N-02' and imbalance_cost_eur > 0.01)
  )
