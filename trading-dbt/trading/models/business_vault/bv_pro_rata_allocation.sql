-- R(a,t) = R(port,t) * G(a,t) / sum G(i,t)

with spine as (
    select
        b.hk_portfolio,
        b.portfolio_id,
        b.hk_asset,
        b.asset_id,
        i.interval_start,
        i.interval_end,
        i.generation_mwh
    from {{ ref('bridge_portfolio_asset') }} b
    inner join {{ ref('bv_asset_interval') }} i
        on i.hk_asset = b.hk_asset
       and i.interval_start >= b.valid_from
       and (b.valid_to is null or i.interval_start < b.valid_to)
),

wholesale as (
    select
        hk_portfolio,
        interval_start,
        sum(revenue_eur) as portfolio_revenue_eur,
        sum(volume_mwh) as portfolio_volume_mwh
    from {{ ref('stg_portfolio_settlement') }}
    where market_code in ('NP_DA_EE', 'NP_ID_EE')
    group by hk_portfolio, interval_start
),

weighted as (
    select
        s.hk_portfolio,
        s.portfolio_id,
        s.hk_asset,
        s.asset_id,
        s.interval_start,
        s.interval_end,
        s.generation_mwh,
        w.portfolio_revenue_eur,
        w.portfolio_volume_mwh,
        sum(s.generation_mwh) over (
            partition by s.hk_portfolio, s.interval_start
        ) as portfolio_generation_mwh
    from spine s
    inner join wholesale w
        on w.hk_portfolio = s.hk_portfolio
       and w.interval_start = s.interval_start
)

select
    hk_portfolio,
    portfolio_id,
    hk_asset,
    asset_id,
    interval_start,
    interval_end,
    generation_mwh,
    portfolio_generation_mwh,
    portfolio_revenue_eur,
    portfolio_volume_mwh,
    case
        when portfolio_generation_mwh = 0 then 0
        else portfolio_revenue_eur * generation_mwh / portfolio_generation_mwh
    end as allocated_revenue_eur
from weighted
