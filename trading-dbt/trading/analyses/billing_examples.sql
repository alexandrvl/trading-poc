-- Asset bill for the short portfolio quarter.
select *
from {{ ref('mart_asset_internal_billing') }}
where portfolio_id = 'Wind_EE_North'
  and interval_start = timestamp '2026-06-01 12:00:00'
order by asset_id;

-- Curtailment compensation for WT-EE-N-01.
select *
from {{ ref('mart_curtailment_compensation') }}
order by interval_start;

-- Portfolio cash versus the sum of asset bills.
select *
from {{ ref('mart_portfolio_reconciliation') }}
order by portfolio_id, interval_start;
