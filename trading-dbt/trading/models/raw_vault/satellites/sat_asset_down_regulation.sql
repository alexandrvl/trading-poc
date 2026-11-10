{{
    config(
        unique_key=['hk_asset', 'ldts', 'event_id'],
        enabled=(target.type == 'postgres')
    )
}}

with source as (
    select
        hk_asset,
        ldts,
        event_id,
        hashdiff,
        asset_id,
        portfolio_id,
        interval_start,
        interval_end,
        commanded_setpoint_kw,
        reason,
        market_code,
        rsrc
    from {{ ref('stg_down_regulation_events') }}
    where hk_asset is not null
)

{{ satellite_changes(['hk_asset', 'event_id']) }}
