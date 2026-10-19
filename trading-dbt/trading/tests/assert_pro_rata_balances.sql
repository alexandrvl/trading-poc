select
    portfolio_id,
    interval_start,
    sum_alloc,
    portfolio_revenue_eur
from (
    select
        portfolio_id,
        interval_start,
        sum(allocated_revenue_eur) as sum_alloc,
        max(portfolio_revenue_eur) as portfolio_revenue_eur
    from {{ ref('bv_pro_rata_allocation') }}
    group by portfolio_id, interval_start
)
where abs(sum_alloc - portfolio_revenue_eur) > 0.01
