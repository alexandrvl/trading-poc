select 'missing parallel forecast rows' as issue
where (
    select count(*)
    from (
        select hk_asset, ldts
        from {{ ref('sat_asset_meteologica_forecast') }}
        group by hk_asset, ldts
        having count(*) > 1
    )
) = 0
