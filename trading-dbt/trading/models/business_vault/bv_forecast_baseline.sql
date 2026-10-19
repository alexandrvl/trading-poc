{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key=['hk_asset', 'type_code', 'target_timestamp']
    )
}}

-- Current forecast per asset, ensemble and target time.
-- delete+insert replaces a key when Meteologica republishes that target.
-- A run with no new forecast rows merges nothing.

with ranked as (
    select
        hk_asset,
        asset_id,
        type_code,
        target_timestamp,
        expected_power_kw,
        wind_speed_m_s,
        ghi_w_m2,
        hashdiff,
        ldts,
        rsrc,
        row_number() over (
            partition by hk_asset, type_code, target_timestamp
            order by ldts desc
        ) as rn
    from {{ ref('sat_asset_meteologica_forecast') }}
)

select
    hk_asset,
    asset_id,
    type_code,
    target_timestamp,
    expected_power_kw,
    wind_speed_m_s,
    ghi_w_m2,
    hashdiff,
    ldts,
    ldts as source_ldts,
    rsrc
from ranked
where rn = 1
{% if vault_is_unchanged(relation_max_ldts(ref('sat_asset_meteologica_forecast'))) | trim == 'True' %}
    and 1 = 0
{% endif %}
