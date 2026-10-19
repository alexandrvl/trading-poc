-- Point-in-time pointers for one asset and one 15-minute snapshot.
-- Billing models equi-join satellites on these load timestamps.

with snapshots as (
    select hk_asset, interval_start as snapshot_ts, telemetry_ldts
    from {{ ref('bv_asset_generation_15m') }}
),

details_ranked as (
    select
        s.hk_asset,
        s.snapshot_ts,
        d.ldts as asset_details_ldts,
        row_number() over (
            partition by s.hk_asset, s.snapshot_ts
            order by d.ldts desc
        ) as rn
    from snapshots s
    inner join {{ ref('sat_asset_details') }} d
        on d.hk_asset = s.hk_asset
       and d.ldts <= s.snapshot_ts
),

capacity_ranked as (
    select
        s.hk_asset,
        s.snapshot_ts,
        c.ldts as capacity_ldts,
        row_number() over (
            partition by s.hk_asset, s.snapshot_ts
            order by c.ldts desc
        ) as rn
    from snapshots s
    inner join {{ ref('sat_asset_capacity_status') }} c
        on c.hk_asset = s.hk_asset
       and c.ldts <= s.snapshot_ts
),

forecast_ranked as (
    select
        s.hk_asset,
        s.snapshot_ts,
        f.type_code,
        f.ldts as forecast_ldts,
        row_number() over (
            partition by s.hk_asset, s.snapshot_ts, f.type_code
            order by f.ldts desc
        ) as rn
    from snapshots s
    inner join {{ ref('sat_asset_meteologica_forecast') }} f
        on f.hk_asset = s.hk_asset
       and f.target_timestamp = s.snapshot_ts
       and f.ldts <= s.snapshot_ts
       and f.type_code in ('Ensemble_P50', 'Intraday_Downscale')
)

select
    s.hk_asset,
    s.snapshot_ts,
    s.telemetry_ldts,
    d.asset_details_ldts,
    c.capacity_ldts,
    p50.forecast_ldts as forecast_p50_ldts,
    intra.forecast_ldts as forecast_intraday_ldts
from snapshots s
left join details_ranked d
    on d.hk_asset = s.hk_asset
   and d.snapshot_ts = s.snapshot_ts
   and d.rn = 1
left join capacity_ranked c
    on c.hk_asset = s.hk_asset
   and c.snapshot_ts = s.snapshot_ts
   and c.rn = 1
left join forecast_ranked p50
    on p50.hk_asset = s.hk_asset
   and p50.snapshot_ts = s.snapshot_ts
   and p50.type_code = 'Ensemble_P50'
   and p50.rn = 1
left join forecast_ranked intra
    on intra.hk_asset = s.hk_asset
   and intra.snapshot_ts = s.snapshot_ts
   and intra.type_code = 'Intraday_Downscale'
   and intra.rn = 1
