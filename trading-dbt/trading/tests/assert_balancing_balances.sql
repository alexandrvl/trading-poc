with allocated as (
    select
        portfolio_id,
        interval_start,
        sum(
            afrr_capacity_eur + afrr_energy_eur
            + mfrr_capacity_eur + mfrr_energy_eur
            + fcr_revenue_eur + capacity_revenue_eur
        ) as allocated_cash,
        sum(capacity_penalty_eur) as allocated_penalty
    from {{ ref('bv_balancing_revenue') }}
    group by portfolio_id, interval_start
),

expected as (
    select
        portfolio_id,
        interval_start,
        sum(capacity_revenue_eur + energy_revenue_eur) as expected_cash,
        sum(penalty_eur) as expected_penalty
    from {{ ref('stg_balancing_settlement') }}
    group by portfolio_id, interval_start
)

select
    coalesce(e.portfolio_id, a.portfolio_id) as portfolio_id,
    coalesce(e.interval_start, a.interval_start) as interval_start,
    a.allocated_cash,
    e.expected_cash,
    a.allocated_penalty,
    e.expected_penalty
from expected e
full outer join allocated a
    on a.portfolio_id = e.portfolio_id
   and a.interval_start = e.interval_start
where a.portfolio_id is null
   or e.portfolio_id is null
   or abs(a.allocated_cash - e.expected_cash) > 0.01
   or abs(a.allocated_penalty - e.expected_penalty) > 0.01
