{% macro upstream_watermark() -%}
select greatest(
    coalesce((select max(ldts) from {{ ref('sat_asset_emsys_telemetry') }}), timestamp '1970-01-01 00:00:00'),
    coalesce((select max(ldts) from {{ ref('sat_asset_meteologica_forecast') }}), timestamp '1970-01-01 00:00:00'),
    coalesce((select max(ldts) from {{ ref('sat_asset_capacity_status') }}), timestamp '1970-01-01 00:00:00'),
    coalesce((select max(ldts) from {{ ref('stg_portfolio_settlement') }}), timestamp '1970-01-01 00:00:00'),
    coalesce((select max(ldts) from {{ ref('stg_balancing_settlement') }}), timestamp '1970-01-01 00:00:00'),
    coalesce((select max(ldts) from {{ ref('stg_market_prices') }}), timestamp '1970-01-01 00:00:00')
)
{%- endmacro %}

{% macro relation_max_ldts(relation) -%}
select coalesce((select max(ldts) from {{ relation }}), timestamp '1970-01-01 00:00:00')
{%- endmacro %}
