-- Operational source schema for the electricity-trading lakehouse.
-- Systems represented: Emsys VPP (assets, telemetry, availability),
-- Periotheus (portfolios, orders, settlements) and Meteologica (forecasts).

CREATE SCHEMA IF NOT EXISTS trading;

CREATE TABLE trading.assets (
    asset_id              varchar(50) PRIMARY KEY,
    asset_name            varchar(200) NOT NULL,
    technology            varchar(20)  NOT NULL,
    nominal_power_kw      double precision NOT NULL,
    latitude              double precision,
    longitude             double precision,
    zone_code             varchar(50),
    turbine_model         varchar(100),
    commissioning_date    timestamp,
    last_modified         timestamp NOT NULL,
    source_system         varchar(50) NOT NULL
);

CREATE TABLE trading.portfolios (
    portfolio_id     varchar(50) PRIMARY KEY,
    portfolio_name   varchar(200) NOT NULL,
    bidding_zone     varchar(50) NOT NULL,
    strategy_module  varchar(50),
    status           varchar(20) NOT NULL,
    valid_from       timestamp NOT NULL,
    last_modified    timestamp NOT NULL,
    source_system    varchar(50) NOT NULL
);

CREATE TABLE trading.portfolio_membership (
    portfolio_id      varchar(50) NOT NULL,
    asset_id          varchar(50) NOT NULL,
    valid_from        timestamp NOT NULL,
    valid_to          timestamp,
    membership_share  double precision NOT NULL,
    last_modified     timestamp NOT NULL,
    source_system     varchar(50) NOT NULL,
    PRIMARY KEY (portfolio_id, asset_id, valid_from)
);

CREATE TABLE trading.markets (
    market_code             varchar(50) PRIMARY KEY,
    market_name             varchar(200) NOT NULL,
    segment                 varchar(50) NOT NULL,
    product_resolution_min  integer NOT NULL,
    tso                     varchar(50),
    currency_code           varchar(10) NOT NULL,
    source_system           varchar(50) NOT NULL
);

CREATE TABLE trading.trade_orders (
    order_id        varchar(50) PRIMARY KEY,
    portfolio_id    varchar(50) NOT NULL,
    market_code     varchar(50) NOT NULL,
    price_eur       double precision NOT NULL,
    volume_mw       double precision NOT NULL,
    delivery_start  timestamp NOT NULL,
    delivery_end    timestamp NOT NULL,
    order_type      varchar(20) NOT NULL,
    direction       varchar(10) NOT NULL,
    order_status    varchar(20) NOT NULL,
    trade_ts        timestamp NOT NULL,
    source_system   varchar(50) NOT NULL
);

CREATE TABLE trading.emsys_telemetry (
    telemetry_id        bigint PRIMARY KEY,
    asset_id            varchar(50) NOT NULL,
    event_ts            timestamp NOT NULL,
    active_power_kw     double precision NOT NULL,
    reactive_power_kvar double precision NOT NULL,
    turbine_status      varchar(40) NOT NULL,
    setpoint_limit_kw   double precision NOT NULL,
    control_mode        varchar(40) NOT NULL,
    source_system       varchar(50) NOT NULL,
    ingested_at         timestamp NOT NULL
);

CREATE TABLE trading.capacity_status (
    asset_id                  varchar(50) NOT NULL,
    status_ts                 timestamp NOT NULL,
    declared_availability_mw  double precision NOT NULL,
    outage_status             varchar(40) NOT NULL,
    derating_factor           double precision NOT NULL,
    source_system             varchar(50) NOT NULL,
    PRIMARY KEY (asset_id, status_ts)
);

CREATE TABLE trading.meteologica_forecast (
    asset_id           varchar(50) NOT NULL,
    forecast_run_ts    timestamp NOT NULL,
    type_code          varchar(40) NOT NULL,
    target_timestamp   timestamp NOT NULL,
    expected_power_kw  double precision NOT NULL,
    wind_speed_m_s     double precision,
    ghi_w_m2           double precision,
    source_system      varchar(50) NOT NULL,
    PRIMARY KEY (asset_id, forecast_run_ts, type_code, target_timestamp)
);

CREATE TABLE trading.portfolio_settlement (
    portfolio_id            varchar(50) NOT NULL,
    market_code             varchar(50) NOT NULL,
    interval_start          timestamp NOT NULL,
    interval_end            timestamp NOT NULL,
    revenue_eur             double precision NOT NULL,
    volume_mwh              double precision NOT NULL,
    imbalance_cost_eur      double precision NOT NULL,
    clearing_price_eur_mwh  double precision NOT NULL,
    loaded_at               timestamp NOT NULL,
    source_system           varchar(50) NOT NULL,
    PRIMARY KEY (portfolio_id, market_code, interval_start)
);

CREATE TABLE trading.balancing_settlement (
    portfolio_id          varchar(50) NOT NULL,
    market_code           varchar(50) NOT NULL,
    interval_start        timestamp NOT NULL,
    interval_end          timestamp NOT NULL,
    capacity_revenue_eur  double precision NOT NULL,
    energy_revenue_eur    double precision NOT NULL,
    penalty_eur           double precision NOT NULL,
    loaded_at             timestamp NOT NULL,
    source_system         varchar(50) NOT NULL,
    PRIMARY KEY (portfolio_id, market_code, interval_start)
);

CREATE TABLE trading.market_prices (
    market_code             varchar(50) NOT NULL,
    interval_start          timestamp NOT NULL,
    interval_end            timestamp NOT NULL,
    clearing_price_eur_mwh  double precision NOT NULL,
    loaded_at               timestamp NOT NULL,
    source_system           varchar(50) NOT NULL,
    PRIMARY KEY (market_code, interval_start)
);
