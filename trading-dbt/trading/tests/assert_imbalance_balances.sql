select
    portfolio_id,
    interval_start,
    sum_cost,
    portfolio_imbalance_cost_eur
from (
    select
        portfolio_id,
        interval_start,
        sum(imbalance_cost_eur) as sum_cost,
        max(portfolio_imbalance_cost_eur) as portfolio_imbalance_cost_eur
    from {{ ref('bv_imbalance_attribution') }}
    group by portfolio_id, interval_start
) summed
where abs(sum_cost - portfolio_imbalance_cost_eur) > 0.01
