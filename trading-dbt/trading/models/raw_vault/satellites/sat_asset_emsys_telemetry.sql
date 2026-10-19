{{
    config(
        materialized='incremental',
        incremental_strategy='append',
        properties={
            "format": "'PARQUET'",
            "partitioning": "ARRAY['day(ldts)']"
        }
    )
}}

-- Append-only journal of Emsys samples. Iceberg partitioning uses Trino's
-- `partitioning` property (the architecture note's partitioned_by name).
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
    hashdiff,
    rsrc
from {{ ref('stg_emsys_telemetry') }}
{% if is_incremental() %}
where ldts > (select coalesce(max(ldts), timestamp '1970-01-01 00:00:00') from {{ this }})
{% endif %}
