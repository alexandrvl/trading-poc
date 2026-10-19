-- Integrate 1-minute active power into the 15-minute billing interval.
-- Energy uses the quarter-hour width, which matches the fixed market interval.

with samples as (
    select
        hk_asset,
        asset_id,
        {{ quarter_hour_start('event_ts') }} as interval_start,
        active_power_kw,
        reactive_power_kvar,
        setpoint_limit_kw,
        control_mode,
        ldts
    from {{ ref('sat_asset_emsys_telemetry') }}
)

select
    hk_asset,
    asset_id,
    interval_start,
    date_add('minute', 15, interval_start) as interval_end,
    avg(active_power_kw) as avg_active_power_kw,
    avg(reactive_power_kvar) as avg_reactive_power_kvar,
    avg(setpoint_limit_kw) as avg_setpoint_limit_kw,
    min(setpoint_limit_kw) as min_setpoint_limit_kw,
    max(case when control_mode = 'EXTERNAL_CONTROL' then 1 else 0 end) as external_control_flag,
    sum(case when control_mode = 'AFRR' then 1 else 0 end) as afrr_sample_count,
    sum(
        case
            when control_mode = 'FCR_AUTONOMOUS' then abs(active_power_kw - setpoint_limit_kw)
            else 0
        end
    ) as fcr_response_kw_sum,
    avg(active_power_kw) * 0.25 / 1000.0 as generation_mwh,
    count(*) as sample_count,
    max(ldts) as telemetry_ldts
from samples
group by hk_asset, asset_id, interval_start
