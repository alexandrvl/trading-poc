-- Lost energy while Elering curtails the asset, valued at the mFRR down price.
-- Baseline is the intraday downscale issued before the interval.

select
    i.hk_asset,
    i.asset_id,
    b.hk_portfolio,
    b.portfolio_id,
    i.interval_start,
    i.interval_end,
    i.generation_mwh as actual_mwh,
    coalesce(i.forecast_intraday_mwh, i.forecast_mwh, 0) as baseline_mwh,
    greatest(
        0,
        coalesce(i.forecast_intraday_mwh, i.forecast_mwh, 0) - i.generation_mwh
    ) as lost_energy_mwh,
    pr.clearing_price_eur_mwh,
    greatest(
        0,
        coalesce(i.forecast_intraday_mwh, i.forecast_mwh, 0) - i.generation_mwh
    ) * pr.clearing_price_eur_mwh as compensation_eur
from {{ ref('bv_asset_interval') }} i
inner join {{ ref('bridge_portfolio_asset') }} b
    on b.hk_asset = i.hk_asset
   and i.interval_start >= b.valid_from
   and (b.valid_to is null or i.interval_start < b.valid_to)
inner join {{ ref('stg_market_prices') }} pr
    on pr.market_code = 'ELERING_mFRR_DOWN'
   and pr.interval_start = i.interval_start
where i.external_control_flag = 1
  and i.nominal_power_kw is not null
  and i.min_setpoint_limit_kw < i.nominal_power_kw
