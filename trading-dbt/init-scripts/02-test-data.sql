-- One operating afternoon, 2026-06-01 12:00-14:00, 1-minute telemetry.
--
-- Wind_EE_North sells a portfolio block. Asset WT-EE-N-02 under-produces
-- against its P50 forecast in the 12:00 quarter, so the imbalance charge
-- lands on that asset. WT-EE-N-01 is curtailed by Elering from 13:00 to
-- 13:30. WT-EE-N-12 moved from Solar_EE_South to Wind_EE_North on 2026-05-01.

INSERT INTO trading.assets (
    asset_id, asset_name, technology, nominal_power_kw, latitude, longitude,
    zone_code, turbine_model, commissioning_date, last_modified, source_system
) VALUES
    ('WT-EE-N-01', 'Narva wind turbine 01', 'WIND', 3000, 59.40, 28.05, 'EE', 'Vestas V150', timestamp '2022-04-01', timestamp '2026-05-15', 'EMSYS_VPP'),
    ('WT-EE-N-02', 'Narva wind turbine 02', 'WIND', 3000, 59.41, 28.06, 'EE', 'Vestas V150', timestamp '2022-04-01', timestamp '2026-05-15', 'EMSYS_VPP'),
    ('WT-EE-N-12', 'Narva wind turbine 12', 'WIND', 2000, 59.42, 28.08, 'EE', 'Nordex N149', timestamp '2021-09-01', timestamp '2026-05-15', 'EMSYS_VPP'),
    ('PV-EE-S-01', 'Parnu solar inverter 01', 'SOLAR', 1500, 58.39, 24.50, 'EE', 'SMA Sunny Central', timestamp '2023-06-01', timestamp '2026-05-15', 'EMSYS_VPP'),
    ('BESS-EE-01', 'Narva battery 01', 'BESS', 1000, 59.39, 28.04, 'EE', 'Tesla Megapack', timestamp '2024-11-01', timestamp '2026-05-15', 'EMSYS_VPP');

INSERT INTO trading.portfolios (
    portfolio_id, portfolio_name, bidding_zone, strategy_module, status,
    valid_from, last_modified, source_system
) VALUES
    ('Wind_EE_North', 'Estonia wind zone 1', 'EE', 'autoTRADER', 'ACTIVE', timestamp '2020-01-01', timestamp '2026-05-15', 'PERIOTHEUS'),
    ('Solar_EE_South', 'Estonia solar south', 'EE', 'autoTRADER', 'ACTIVE', timestamp '2020-01-01', timestamp '2026-05-15', 'PERIOTHEUS');

INSERT INTO trading.portfolio_membership (
    portfolio_id, asset_id, valid_from, valid_to, membership_share, last_modified, source_system
) VALUES
    ('Wind_EE_North', 'WT-EE-N-01', timestamp '2024-01-01', NULL, 1.0, timestamp '2024-01-01', 'PERIOTHEUS'),
    ('Wind_EE_North', 'WT-EE-N-02', timestamp '2024-01-01', NULL, 1.0, timestamp '2024-01-01', 'PERIOTHEUS'),
    ('Wind_EE_North', 'BESS-EE-01', timestamp '2024-11-01', NULL, 1.0, timestamp '2024-11-01', 'PERIOTHEUS'),
    ('Solar_EE_South', 'WT-EE-N-12', timestamp '2024-01-01', timestamp '2026-05-01', 1.0, timestamp '2026-05-01', 'PERIOTHEUS'),
    ('Wind_EE_North', 'WT-EE-N-12', timestamp '2026-05-01', NULL, 1.0, timestamp '2026-05-02', 'PERIOTHEUS'),
    ('Solar_EE_South', 'PV-EE-S-01', timestamp '2024-01-01', NULL, 1.0, timestamp '2024-01-01', 'PERIOTHEUS');

INSERT INTO trading.markets (
    market_code, market_name, segment, product_resolution_min, tso, currency_code, source_system
) VALUES
    ('NP_DA_EE', 'Nord Pool day-ahead Estonia', 'DAY_AHEAD', 15, 'ELERING', 'EUR', 'PERIOTHEUS'),
    ('NP_ID_EE', 'Nord Pool intraday Estonia', 'INTRADAY', 15, 'ELERING', 'EUR', 'PERIOTHEUS'),
    ('ELERING_aFRR_UP', 'Elering aFRR up', 'AFRR', 15, 'ELERING', 'EUR', 'PERIOTHEUS'),
    ('ELERING_aFRR_DOWN', 'Elering aFRR down', 'AFRR', 15, 'ELERING', 'EUR', 'PERIOTHEUS'),
    ('ELERING_mFRR_UP', 'Elering mFRR up', 'MFRR', 15, 'ELERING', 'EUR', 'PERIOTHEUS'),
    ('ELERING_mFRR_DOWN', 'Elering mFRR down', 'MFRR', 15, 'ELERING', 'EUR', 'PERIOTHEUS'),
    ('ELERING_FCR', 'Elering FCR', 'FCR', 15, 'ELERING', 'EUR', 'PERIOTHEUS'),
    ('CAPACITY_MARKET_BALTIC', 'Baltic capacity market', 'CAPACITY', 15, 'ELERING', 'EUR', 'PERIOTHEUS'),
    ('ELERING_IMBALANCE', 'Elering imbalance settlement', 'IMBALANCE', 15, 'ELERING', 'EUR', 'PERIOTHEUS');

INSERT INTO trading.trade_orders (
    order_id, portfolio_id, market_code, price_eur, volume_mw, delivery_start,
    delivery_end, order_type, direction, order_status, trade_ts, source_system
) VALUES
    ('ORD-DA-WIND-001', 'Wind_EE_North', 'NP_DA_EE', 80, 5.0, timestamp '2026-06-01 12:00', timestamp '2026-06-01 14:00', 'BLOCK', 'SELL', 'CONFIRMED', timestamp '2026-05-31 11:00', 'PERIOTHEUS'),
    ('ORD-AFRR-WIND-001', 'Wind_EE_North', 'ELERING_aFRR_UP', 15, 1.0, timestamp '2026-06-01 12:00', timestamp '2026-06-01 14:00', 'SINGLE', 'SELL', 'CONFIRMED', timestamp '2026-05-31 12:00', 'PERIOTHEUS'),
    ('ORD-MFRR-WIND-001', 'Wind_EE_North', 'ELERING_mFRR_DOWN', 95, 2.0, timestamp '2026-06-01 13:00', timestamp '2026-06-01 13:30', 'SINGLE', 'SELL', 'CONFIRMED', timestamp '2026-06-01 12:40', 'PERIOTHEUS'),
    ('ORD-FCR-WIND-001', 'Wind_EE_North', 'ELERING_FCR', 12, 0.5, timestamp '2026-06-01 12:00', timestamp '2026-06-01 14:00', 'SINGLE', 'SELL', 'CONFIRMED', timestamp '2026-05-31 09:00', 'PERIOTHEUS'),
    ('ORD-CAP-WIND-001', 'Wind_EE_North', 'CAPACITY_MARKET_BALTIC', 10, 6.0, timestamp '2026-06-01 12:00', timestamp '2026-06-01 14:00', 'BLOCK', 'SELL', 'CONFIRMED', timestamp '2026-05-01 08:00', 'PERIOTHEUS'),
    ('ORD-DA-SOLAR-001', 'Solar_EE_South', 'NP_DA_EE', 80, 0.9, timestamp '2026-06-01 12:00', timestamp '2026-06-01 14:00', 'SINGLE', 'SELL', 'CONFIRMED', timestamp '2026-05-31 11:05', 'PERIOTHEUS');

CREATE OR REPLACE FUNCTION trading.p50_power_kw(p_asset_id text, p_target timestamp)
RETURNS double precision
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN p_asset_id = 'WT-EE-N-01' AND p_target >= timestamp '2026-06-01 13:00:00' THEN 2500
        WHEN p_asset_id = 'WT-EE-N-01' THEN 2000
        WHEN p_asset_id = 'WT-EE-N-02' THEN 2000
        WHEN p_asset_id = 'WT-EE-N-12' THEN 1800
        WHEN p_asset_id = 'PV-EE-S-01' THEN 900
        ELSE 0
    END::double precision;
$$;

CREATE OR REPLACE FUNCTION trading.sample_telemetry(p_asset_id text, p_ts timestamp)
RETURNS TABLE (
    active_power_kw double precision,
    reactive_power_kvar double precision,
    turbine_status text,
    setpoint_limit_kw double precision,
    control_mode text
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        v.active_power_kw,
        v.active_power_kw * 0.04,
        v.turbine_status,
        v.setpoint_limit_kw,
        v.control_mode
    FROM (
        SELECT
            CASE
                WHEN p_asset_id = 'WT-EE-N-01' AND p_ts >= timestamp '2026-06-01 13:00:00' AND p_ts < timestamp '2026-06-01 13:30:00' THEN 480
                WHEN p_asset_id = 'WT-EE-N-01' AND p_ts >= timestamp '2026-06-01 13:30:00' THEN 2100
                WHEN p_asset_id = 'WT-EE-N-01' AND p_ts >= timestamp '2026-06-01 12:30:00' AND p_ts < timestamp '2026-06-01 12:45:00' THEN 1800
                WHEN p_asset_id = 'WT-EE-N-01' THEN 2000
                WHEN p_asset_id = 'WT-EE-N-02' AND p_ts < timestamp '2026-06-01 13:00:00' THEN 1000
                WHEN p_asset_id = 'WT-EE-N-02' THEN 1500
                WHEN p_asset_id = 'WT-EE-N-12' AND p_ts >= timestamp '2026-06-01 12:15:00' AND p_ts < timestamp '2026-06-01 12:20:00' THEN 2300
                WHEN p_asset_id = 'WT-EE-N-12' THEN 2000
                WHEN p_asset_id = 'PV-EE-S-01' THEN 900
                ELSE 0
            END::double precision AS active_power_kw,
            CASE
                WHEN p_asset_id = 'WT-EE-N-01' AND p_ts >= timestamp '2026-06-01 13:00:00' AND p_ts < timestamp '2026-06-01 13:30:00' THEN 'EXTERNAL_CONTROL'
                WHEN p_asset_id = 'WT-EE-N-02' AND p_ts < timestamp '2026-06-01 13:00:00' THEN 'DERATED'
                WHEN p_asset_id = 'BESS-EE-01' THEN 'STANDBY'
                ELSE 'PRODUCING'
            END AS turbine_status,
            CASE
                WHEN p_asset_id = 'WT-EE-N-01' AND p_ts >= timestamp '2026-06-01 13:00:00' AND p_ts < timestamp '2026-06-01 13:30:00' THEN 500
                WHEN p_asset_id = 'WT-EE-N-01' AND p_ts >= timestamp '2026-06-01 12:30:00' AND p_ts < timestamp '2026-06-01 12:45:00' THEN 1800
                WHEN p_asset_id = 'WT-EE-N-01' THEN 3000
                WHEN p_asset_id = 'WT-EE-N-02' THEN 3000
                WHEN p_asset_id = 'WT-EE-N-12' THEN 2000
                WHEN p_asset_id = 'PV-EE-S-01' THEN 1500
                ELSE 0
            END::double precision AS setpoint_limit_kw,
            CASE
                WHEN p_asset_id = 'WT-EE-N-01' AND p_ts >= timestamp '2026-06-01 13:00:00' AND p_ts < timestamp '2026-06-01 13:30:00' THEN 'EXTERNAL_CONTROL'
                WHEN p_asset_id = 'WT-EE-N-01' AND p_ts >= timestamp '2026-06-01 12:30:00' AND p_ts < timestamp '2026-06-01 12:45:00' THEN 'AFRR'
                WHEN p_asset_id = 'WT-EE-N-12' AND p_ts >= timestamp '2026-06-01 12:15:00' AND p_ts < timestamp '2026-06-01 12:20:00' THEN 'FCR_AUTONOMOUS'
                ELSE 'NORMAL'
            END AS control_mode
    ) v;
$$;

INSERT INTO trading.emsys_telemetry (
    telemetry_id, asset_id, event_ts, active_power_kw, reactive_power_kvar,
    turbine_status, setpoint_limit_kw, control_mode, source_system, ingested_at
)
SELECT
    row_number() OVER (ORDER BY a.asset_id, m.event_ts),
    a.asset_id,
    m.event_ts,
    s.active_power_kw,
    s.reactive_power_kvar,
    s.turbine_status,
    s.setpoint_limit_kw,
    s.control_mode,
    'EMSYS_VPP',
    m.event_ts + interval '2 seconds'
FROM generate_series(
        timestamp '2026-06-01 12:00:00',
        timestamp '2026-06-01 13:59:00',
        interval '1 minute'
     ) AS m(event_ts)
CROSS JOIN trading.assets a
CROSS JOIN LATERAL trading.sample_telemetry(a.asset_id, m.event_ts) AS s;

INSERT INTO trading.capacity_status (
    asset_id, status_ts, declared_availability_mw, outage_status, derating_factor, source_system
) VALUES
    ('WT-EE-N-01', timestamp '2026-06-01 00:00', 3.0, 'AVAILABLE', 1.0, 'EMSYS_VPP'),
    ('WT-EE-N-02', timestamp '2026-06-01 00:00', 3.0, 'AVAILABLE', 1.0, 'EMSYS_VPP'),
    ('WT-EE-N-02', timestamp '2026-06-01 12:00', 1.5, 'DERATED', 0.5, 'EMSYS_VPP'),
    ('WT-EE-N-02', timestamp '2026-06-01 13:00', 3.0, 'AVAILABLE', 1.0, 'EMSYS_VPP'),
    ('WT-EE-N-12', timestamp '2026-06-01 00:00', 2.0, 'AVAILABLE', 1.0, 'EMSYS_VPP'),
    ('PV-EE-S-01', timestamp '2026-06-01 00:00', 1.5, 'AVAILABLE', 1.0, 'EMSYS_VPP'),
    ('BESS-EE-01', timestamp '2026-06-01 00:00', 1.0, 'AVAILABLE', 1.0, 'EMSYS_VPP');

INSERT INTO trading.meteologica_forecast (
    asset_id, forecast_run_ts, type_code, target_timestamp,
    expected_power_kw, wind_speed_m_s, ghi_w_m2, source_system
)
SELECT
    a.asset_id,
    runs.forecast_run_ts,
    runs.type_code,
    t.target_timestamp,
    runs.factor * trading.p50_power_kw(a.asset_id, t.target_timestamp),
    CASE a.technology WHEN 'SOLAR' THEN 2.1 WHEN 'BESS' THEN 0 ELSE 8.4 END,
    CASE a.technology WHEN 'SOLAR' THEN 640 ELSE 0 END,
    'METEOLOGICA'
FROM trading.assets a
CROSS JOIN generate_series(
    timestamp '2026-06-01 12:00:00',
    timestamp '2026-06-01 13:45:00',
    interval '15 minutes'
) AS t(target_timestamp)
CROSS JOIN (
    VALUES
        (timestamp '2026-06-01 06:00:00', 'Ensemble_P10', 0.70::double precision),
        (timestamp '2026-06-01 06:00:00', 'Ensemble_P50', 1.00::double precision),
        (timestamp '2026-06-01 06:00:00', 'Ensemble_P90', 1.15::double precision),
        (timestamp '2026-06-01 11:30:00', 'Intraday_Downscale', 1.00::double precision),
        (timestamp '2026-06-01 18:00:00', 'Ensemble_P90', 1.25::double precision)
) AS runs(forecast_run_ts, type_code, factor);

WITH quarters AS (
    SELECT
        m.portfolio_id,
        date_trunc('hour', t.event_ts)
            + ((extract(minute FROM t.event_ts)::int / 15) * interval '15 minutes') AS interval_start,
        avg(t.active_power_kw) * 0.25 / 1000.0 AS generation_mwh,
        trading.p50_power_kw(
            t.asset_id,
            date_trunc('hour', t.event_ts)
                + ((extract(minute FROM t.event_ts)::int / 15) * interval '15 minutes')
        ) * 0.25 / 1000.0 AS forecast_mwh
    FROM trading.emsys_telemetry t
    JOIN trading.portfolio_membership m
      ON m.asset_id = t.asset_id
     AND t.event_ts >= m.valid_from
     AND (m.valid_to IS NULL OR t.event_ts < m.valid_to)
    GROUP BY m.portfolio_id, t.asset_id, 2
),
portfolios AS (
    SELECT
        portfolio_id,
        interval_start,
        sum(generation_mwh) AS generation_mwh,
        sum(generation_mwh - forecast_mwh) AS delta_mwh
    FROM quarters
    GROUP BY portfolio_id, interval_start
)
INSERT INTO trading.portfolio_settlement (
    portfolio_id, market_code, interval_start, interval_end, revenue_eur,
    volume_mwh, imbalance_cost_eur, clearing_price_eur_mwh, loaded_at, source_system
)
SELECT
    portfolio_id,
    'NP_DA_EE',
    interval_start,
    interval_start + interval '15 minutes',
    generation_mwh * 80.0,
    generation_mwh,
    0,
    80,
    timestamp '2026-06-01 16:00:00',
    'PERIOTHEUS'
FROM portfolios
UNION ALL
SELECT
    portfolio_id,
    'ELERING_IMBALANCE',
    interval_start,
    interval_start + interval '15 minutes',
    0,
    delta_mwh,
    abs(delta_mwh) * 40.0,
    40,
    timestamp '2026-06-01 16:05:00',
    'PERIOTHEUS'
FROM portfolios;

INSERT INTO trading.balancing_settlement (
    portfolio_id, market_code, interval_start, interval_end,
    capacity_revenue_eur, energy_revenue_eur, penalty_eur, loaded_at, source_system
)
SELECT
    s.portfolio_id,
    p.market_code,
    s.interval_start,
    s.interval_end,
    p.capacity_revenue_eur,
    CASE
        WHEN p.market_code = 'ELERING_aFRR_UP'
         AND s.portfolio_id = 'Wind_EE_North'
         AND s.interval_start = timestamp '2026-06-01 12:30:00' THEN 5.0
        ELSE 0
    END,
    CASE
        WHEN p.market_code = 'CAPACITY_MARKET_BALTIC'
         AND s.portfolio_id = 'Wind_EE_North'
         AND s.interval_start < timestamp '2026-06-01 13:00:00' THEN 6.0
        ELSE 0
    END,
    timestamp '2026-06-01 16:10:00',
    'PERIOTHEUS'
FROM trading.portfolio_settlement s
JOIN (
    VALUES
        ('ELERING_aFRR_UP', 12.0::double precision),
        ('ELERING_mFRR_UP', 3.0::double precision),
        ('ELERING_FCR', 4.0::double precision),
        ('CAPACITY_MARKET_BALTIC', 10.0::double precision)
) AS p(market_code, capacity_revenue_eur)
  ON s.market_code = 'NP_DA_EE'
 AND (
        s.portfolio_id = 'Wind_EE_North'
        OR p.market_code = 'CAPACITY_MARKET_BALTIC'
     );

INSERT INTO trading.market_prices (
    market_code, interval_start, interval_end, clearing_price_eur_mwh, loaded_at, source_system
)
SELECT
    prices.market_code,
    s.interval_start,
    s.interval_end,
    CASE
        WHEN prices.market_code = 'ELERING_mFRR_DOWN'
         AND s.interval_start >= timestamp '2026-06-01 13:00:00'
         AND s.interval_start < timestamp '2026-06-01 13:30:00' THEN 95
        WHEN prices.market_code = 'ELERING_mFRR_DOWN' THEN 40
        ELSE 80
    END,
    timestamp '2026-06-01 16:15:00',
    'PERIOTHEUS'
FROM trading.portfolio_settlement s
CROSS JOIN (
    VALUES ('NP_DA_EE'), ('ELERING_mFRR_DOWN')
) AS prices(market_code)
WHERE s.market_code = 'NP_DA_EE'
  AND s.portfolio_id = 'Wind_EE_North';
