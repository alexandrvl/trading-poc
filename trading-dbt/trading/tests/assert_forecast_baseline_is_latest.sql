with latest as (
    select
        hk_asset,
        type_code,
        target_timestamp,
        expected_power_kw
    from (
        select
            hk_asset,
            type_code,
            target_timestamp,
            expected_power_kw,
            row_number() over (
                partition by hk_asset, type_code, target_timestamp
                order by ldts desc
            ) as rn
        from {{ ref('sat_asset_meteologica_forecast') }}
    )
    where rn = 1
)

select
    coalesce(b.hk_asset, l.hk_asset) as hk_asset,
    coalesce(b.type_code, l.type_code) as type_code,
    coalesce(b.target_timestamp, l.target_timestamp) as target_timestamp
from {{ ref('bv_forecast_baseline') }} b
full outer join latest l
    on b.hk_asset = l.hk_asset
   and b.type_code = l.type_code
   and b.target_timestamp = l.target_timestamp
where b.hk_asset is null
   or l.hk_asset is null
   or abs(b.expected_power_kw - l.expected_power_kw) > 0.001
