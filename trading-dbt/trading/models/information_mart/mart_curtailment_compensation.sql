select
    asset_id,
    portfolio_id,
    interval_start,
    interval_end,
    actual_mwh,
    baseline_mwh,
    lost_energy_mwh,
    clearing_price_eur_mwh,
    compensation_eur
from {{ ref('bv_down_regulation') }}
