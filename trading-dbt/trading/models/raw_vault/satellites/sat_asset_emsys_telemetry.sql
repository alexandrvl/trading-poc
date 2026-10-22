{{
    config(
        materialized='incremental',
        incremental_strategy='append',
        properties=iceberg_properties('ldts')
    )
}}

-- Append-only journal of Emsys samples.
select
    hk_asset,
    ldts,
    asset_id,
    telemetry_id,
    event_ts,
    active_power_kw,
    reactive_power_kvar,
    turbine_status,
    setpoint_limit_kw,
    control_mode,
    {% if target.type == 'postgres' %}
    soc_percent,
    degradation_cost_eur,
    availability_status,
    {% endif %}
    hashdiff,
    rsrc
from {{ ref('stg_emsys_telemetry') }}
{% if is_incremental() %}
where ldts > (select coalesce(max(ldts), timestamp '1970-01-01 00:00:00') from {{ this }})
{% endif %}
