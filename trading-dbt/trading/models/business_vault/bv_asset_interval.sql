-- Asset state for one billing interval. Forecast and availability come from
-- PIT equi-joins, so a forecast revised after delivery does not change history.

with details as (
    select
        hk_asset,
        ldts,
        asset_name,
        technology,
        nominal_power_kw,
        zone_code
    from {{ ref('sat_asset_details') }}
),

forecasts as (
    select
        hk_asset,
        ldts,
        type_code,
        target_timestamp,
        expected_power_kw,
        wind_speed_m_s,
        ghi_w_m2
    from {{ ref('sat_asset_meteologica_forecast') }}
),

capacity as (
    select
        hk_asset,
        ldts,
        declared_availability_mw,
        outage_status,
        derating_factor
    from {{ ref('sat_asset_capacity_status') }}
)

select
    g.hk_asset,
    g.asset_id,
    g.interval_start,
    g.interval_end,
    g.avg_active_power_kw,
    g.avg_setpoint_limit_kw,
    g.min_setpoint_limit_kw,
    g.external_control_flag,
    g.afrr_sample_count,
    g.fcr_response_kw_sum,
    g.generation_mwh,
    g.sample_count,
    d.asset_name,
    d.technology,
    d.nominal_power_kw,
    d.zone_code,
    p50.expected_power_kw as forecast_p50_kw,
    p50.wind_speed_m_s,
    p50.ghi_w_m2,
    coalesce(p50.expected_power_kw, 0) * 0.25 / 1000.0 as forecast_mwh,
    intra.expected_power_kw as forecast_intraday_kw,
    intra.expected_power_kw * 0.25 / 1000.0 as forecast_intraday_mwh,
    g.generation_mwh - coalesce(p50.expected_power_kw, 0) * 0.25 / 1000.0 as delta_mwh,
    c.declared_availability_mw,
    c.outage_status,
    c.derating_factor
from {{ ref('bv_asset_generation_15m') }} g
inner join {{ ref('pit_asset') }} p
    on p.hk_asset = g.hk_asset
   and p.snapshot_ts = g.interval_start
left join details d
    on d.hk_asset = p.hk_asset
   and d.ldts = p.asset_details_ldts
left join forecasts p50
    on p50.hk_asset = p.hk_asset
   and p50.ldts = p.forecast_p50_ldts
   and p50.type_code = 'Ensemble_P50'
   and p50.target_timestamp = p.snapshot_ts
left join forecasts intra
    on intra.hk_asset = p.hk_asset
   and intra.ldts = p.forecast_intraday_ldts
   and intra.type_code = 'Intraday_Downscale'
   and intra.target_timestamp = p.snapshot_ts
left join capacity c
    on c.hk_asset = p.hk_asset
   and c.ldts = p.capacity_ldts
