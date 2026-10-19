with effectivity as (
    select
        hk_link_portfolio_asset,
        valid_from,
        valid_to,
        membership_share
    from (
        select
            hk_link_portfolio_asset,
            valid_from,
            valid_to,
            membership_share,
            row_number() over (
                partition by hk_link_portfolio_asset, valid_from
                order by ldts desc
            ) as rn
        from {{ ref('sat_link_portfolio_asset') }}
    )
    where rn = 1
)

select
    l.hk_link_portfolio_asset,
    l.hk_portfolio,
    hp.portfolio_id,
    l.hk_asset,
    ha.asset_id,
    e.valid_from,
    e.valid_to,
    e.membership_share
from {{ ref('link_portfolio_asset') }} l
inner join effectivity e
    on e.hk_link_portfolio_asset = l.hk_link_portfolio_asset
inner join {{ ref('hub_portfolio') }} hp
    on hp.hk_portfolio = l.hk_portfolio
inner join {{ ref('hub_asset') }} ha
    on ha.hk_asset = l.hk_asset
