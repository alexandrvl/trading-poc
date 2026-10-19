select
    asset_id,
    portfolio_id,
    interval_start,
    net_revenue_eur
from {{ ref('bv_asset_net_revenue') }}
where abs(
    net_revenue_eur - (
        allocated_revenue_eur
        - imbalance_cost_eur
        + afrr_capacity_eur
        + afrr_energy_eur
        + mfrr_capacity_eur
        + mfrr_energy_eur
        + fcr_revenue_eur
        + capacity_revenue_eur
        - capacity_penalty_eur
        + curtailment_compensation_eur
    )
) > 0.01
