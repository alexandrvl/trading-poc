-- Split portfolio balancing cash onto assets.
-- Readiness payments follow declared availability.
-- aFRR energy follows minutes under aFRR control.
-- FCR follows autonomous response, and falls back to availability.
-- Capacity penalties follow megawatts declared unavailable.

with bridged as (
    select
        b.hk_portfolio,
        b.portfolio_id,
        b.hk_asset,
        b.asset_id,
        i.interval_start,
        coalesce(i.declared_availability_mw, 0) as availability_mw,
        {{ as_double('coalesce(i.afrr_sample_count, 0)') }} as afrr_weight,
        coalesce(i.fcr_response_kw_sum, 0) as fcr_weight,
        case
            when coalesce(i.outage_status, 'AVAILABLE') = 'AVAILABLE' then 0
            else greatest(
                coalesce(i.nominal_power_kw, 0) / 1000.0 - coalesce(i.declared_availability_mw, 0),
                0
            )
        end as penalty_weight
    from {{ ref('bridge_portfolio_asset') }} b
    inner join {{ ref('bv_asset_interval') }} i
        on i.hk_asset = b.hk_asset
       and i.interval_start >= b.valid_from
       and (b.valid_to is null or i.interval_start < b.valid_to)
),

products as (
    select
        hk_portfolio,
        interval_start,
        case
            when market_code in ('ELERING_aFRR_UP', 'ELERING_aFRR_DOWN') then 'afrr'
            when market_code in ('ELERING_mFRR_UP', 'ELERING_mFRR_DOWN') then 'mfrr'
            when market_code = 'ELERING_FCR' then 'fcr'
            when market_code = 'CAPACITY_MARKET_BALTIC' then 'capacity'
        end as product,
        sum(capacity_revenue_eur) as capacity_revenue_eur,
        sum(energy_revenue_eur) as energy_revenue_eur,
        sum(penalty_eur) as penalty_eur
    from {{ ref('stg_balancing_settlement') }}
    group by 1, 2, 3
),

joined as (
    select
        br.hk_portfolio,
        br.portfolio_id,
        br.hk_asset,
        br.asset_id,
        br.interval_start,
        pr.product,
        br.availability_mw,
        case
            when pr.product = 'afrr' then br.afrr_weight
            when pr.product = 'fcr' then br.fcr_weight
            else br.availability_mw
        end as energy_weight,
        br.penalty_weight,
        pr.capacity_revenue_eur as product_capacity_eur,
        pr.energy_revenue_eur as product_energy_eur,
        pr.penalty_eur as product_penalty_eur
    from bridged br
    inner join products pr
        on pr.hk_portfolio = br.hk_portfolio
       and pr.interval_start = br.interval_start
    where pr.product is not null
),

weighted as (
    select
        joined.*,
        sum(availability_mw) over (
            partition by hk_portfolio, interval_start, product
        ) as availability_sum,
        sum(energy_weight) over (
            partition by hk_portfolio, interval_start, product
        ) as energy_weight_sum,
        sum(penalty_weight) over (
            partition by hk_portfolio, interval_start, product
        ) as penalty_weight_sum
    from joined
),

allocated as (
    select
        hk_portfolio,
        portfolio_id,
        hk_asset,
        asset_id,
        interval_start,
        product,
        case
            when product = 'fcr' and energy_weight_sum > 0
                then product_capacity_eur * energy_weight / energy_weight_sum
            when availability_sum > 0
                then product_capacity_eur * availability_mw / availability_sum
            else 0
        end as allocated_capacity_eur,
        case
            when energy_weight_sum > 0
                then product_energy_eur * energy_weight / energy_weight_sum
            when availability_sum > 0
                then product_energy_eur * availability_mw / availability_sum
            else 0
        end as allocated_energy_eur,
        case
            when penalty_weight_sum > 0
                then product_penalty_eur * penalty_weight / penalty_weight_sum
            else 0
        end as allocated_penalty_eur
    from weighted
)

select
    hk_portfolio,
    portfolio_id,
    hk_asset,
    asset_id,
    interval_start,
    sum(case when product = 'afrr' then allocated_capacity_eur else 0 end) as afrr_capacity_eur,
    sum(case when product = 'afrr' then allocated_energy_eur else 0 end) as afrr_energy_eur,
    sum(case when product = 'mfrr' then allocated_capacity_eur else 0 end) as mfrr_capacity_eur,
    sum(case when product = 'mfrr' then allocated_energy_eur else 0 end) as mfrr_energy_eur,
    sum(case when product = 'fcr' then allocated_capacity_eur + allocated_energy_eur else 0 end) as fcr_revenue_eur,
    sum(case when product = 'capacity' then allocated_capacity_eur else 0 end) as capacity_revenue_eur,
    sum(allocated_penalty_eur) as capacity_penalty_eur
from allocated
group by hk_portfolio, portfolio_id, hk_asset, asset_id, interval_start
