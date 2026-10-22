{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['hk_asset', 'hk_portfolio', 'interval_start'],
        properties=iceberg_properties('interval_start')
    )
}}

-- Asset internal billing for one 15-minute interval.
-- Merge so a corrected clearing price updates the same asset and interval.
-- When upstream load timestamps have not moved, the batch is empty.

with final as (
    select
        pro.hk_asset,
        pro.asset_id,
        pro.hk_portfolio,
        pro.portfolio_id,
        pro.interval_start,
        pro.interval_end,
        pro.generation_mwh,
        pro.allocated_revenue_eur,
        pro.portfolio_revenue_eur,
        coalesce(imb.imbalance_cost_eur, 0) as imbalance_cost_eur,
        coalesce(imb.portfolio_imbalance_cost_eur, 0) as portfolio_imbalance_cost_eur,
        coalesce(imb.portfolio_delta_mwh, 0) as portfolio_delta_mwh,
        coalesce(bal.afrr_capacity_eur, 0) as afrr_capacity_eur,
        coalesce(bal.afrr_energy_eur, 0) as afrr_energy_eur,
        coalesce(bal.mfrr_capacity_eur, 0) as mfrr_capacity_eur,
        coalesce(bal.mfrr_energy_eur, 0) as mfrr_energy_eur,
        coalesce(bal.fcr_revenue_eur, 0) as fcr_revenue_eur,
        coalesce(bal.capacity_revenue_eur, 0) as capacity_revenue_eur,
        coalesce(bal.capacity_penalty_eur, 0) as capacity_penalty_eur,
        coalesce(curt.lost_energy_mwh, 0) as lost_energy_mwh,
        coalesce(curt.compensation_eur, 0) as curtailment_compensation_eur,
        pro.allocated_revenue_eur
            - coalesce(imb.imbalance_cost_eur, 0)
            + coalesce(bal.afrr_capacity_eur, 0)
            + coalesce(bal.afrr_energy_eur, 0)
            + coalesce(bal.mfrr_capacity_eur, 0)
            + coalesce(bal.mfrr_energy_eur, 0)
            + coalesce(bal.fcr_revenue_eur, 0)
            + coalesce(bal.capacity_revenue_eur, 0)
            - coalesce(bal.capacity_penalty_eur, 0)
            + coalesce(curt.compensation_eur, 0) as net_revenue_eur,
        ({{ upstream_watermark() }}) as source_ldts
    from {{ ref('bv_pro_rata_allocation') }} pro
    left join {{ ref('bv_imbalance_attribution') }} imb
        on imb.hk_asset = pro.hk_asset
       and imb.hk_portfolio = pro.hk_portfolio
       and imb.interval_start = pro.interval_start
    left join {{ ref('bv_balancing_revenue') }} bal
        on bal.hk_asset = pro.hk_asset
       and bal.hk_portfolio = pro.hk_portfolio
       and bal.interval_start = pro.interval_start
    left join {{ ref('bv_down_regulation') }} curt
        on curt.hk_asset = pro.hk_asset
       and curt.hk_portfolio = pro.hk_portfolio
       and curt.interval_start = pro.interval_start
)

select *
from final
{% if vault_is_unchanged(upstream_watermark()) | trim == 'True' %}
where 1 = 0
{% endif %}
