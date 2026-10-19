-- Imbalance cost is shared only by assets whose error has the same sign
-- as the portfolio error.
-- weight(a) = max(0, sign(delta_port) * delta(a))

with spine as (
    select
        b.hk_portfolio,
        b.portfolio_id,
        b.hk_asset,
        b.asset_id,
        i.interval_start,
        i.generation_mwh,
        i.forecast_mwh,
        i.delta_mwh
    from {{ ref('bridge_portfolio_asset') }} b
    inner join {{ ref('bv_asset_interval') }} i
        on i.hk_asset = b.hk_asset
       and i.interval_start >= b.valid_from
       and (b.valid_to is null or i.interval_start < b.valid_to)
),

imbalance as (
    select
        hk_portfolio,
        interval_start,
        sum(imbalance_cost_eur) as portfolio_imbalance_cost_eur
    from {{ ref('stg_portfolio_settlement') }}
    where market_code = 'ELERING_IMBALANCE'
    group by hk_portfolio, interval_start
),

scored as (
    select
        s.hk_portfolio,
        s.portfolio_id,
        s.hk_asset,
        s.asset_id,
        s.interval_start,
        s.generation_mwh,
        s.forecast_mwh,
        s.delta_mwh,
        imb.portfolio_imbalance_cost_eur,
        sum(s.delta_mwh) over (
            partition by s.hk_portfolio, s.interval_start
        ) as portfolio_delta_mwh
    from spine s
    inner join imbalance imb
        on imb.hk_portfolio = s.hk_portfolio
       and imb.interval_start = s.interval_start
),

weighted as (
    select
        scored.*,
        greatest(0, sign(portfolio_delta_mwh) * delta_mwh) as deviation_weight,
        sum(greatest(0, sign(portfolio_delta_mwh) * delta_mwh)) over (
            partition by hk_portfolio, interval_start
        ) as deviation_weight_sum
    from scored
)

select
    hk_portfolio,
    portfolio_id,
    hk_asset,
    asset_id,
    interval_start,
    generation_mwh,
    forecast_mwh,
    delta_mwh,
    portfolio_delta_mwh,
    deviation_weight,
    portfolio_imbalance_cost_eur,
    case
        when deviation_weight_sum = 0 then 0
        else portfolio_imbalance_cost_eur * deviation_weight / deviation_weight_sum
    end as imbalance_cost_eur
from weighted
