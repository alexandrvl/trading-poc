select
    portfolio_id,
    interval_start,
    sum(generation_mwh) as generation_mwh,
    sum(allocated_revenue_eur) as allocated_revenue_eur,
    max(portfolio_revenue_eur) as portfolio_revenue_eur,
    sum(imbalance_cost_eur) as imbalance_cost_eur,
    max(portfolio_imbalance_cost_eur) as portfolio_imbalance_cost_eur,
    sum(afrr_capacity_eur + afrr_energy_eur) as afrr_eur,
    sum(mfrr_capacity_eur + mfrr_energy_eur) as mfrr_eur,
    sum(fcr_revenue_eur) as fcr_eur,
    sum(capacity_revenue_eur) as capacity_eur,
    sum(capacity_penalty_eur) as capacity_penalty_eur,
    sum(lost_energy_mwh) as lost_energy_mwh,
    sum(curtailment_compensation_eur) as curtailment_compensation_eur,
    sum(net_revenue_eur) as net_revenue_eur
from {{ ref('bv_asset_net_revenue') }}
group by portfolio_id, interval_start
