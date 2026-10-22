-- Interactive PoC extensions. Additive: existing tables stay, new columns
-- and event tables support live VPP / forecast / ETRM simulators.

CREATE SEQUENCE IF NOT EXISTS trading.emsys_telemetry_id_seq;

SELECT setval(
    'trading.emsys_telemetry_id_seq',
    COALESCE((SELECT MAX(telemetry_id) FROM trading.emsys_telemetry), 1)
);

ALTER TABLE trading.emsys_telemetry
    ALTER COLUMN telemetry_id SET DEFAULT nextval('trading.emsys_telemetry_id_seq');

ALTER SEQUENCE trading.emsys_telemetry_id_seq
    OWNED BY trading.emsys_telemetry.telemetry_id;

ALTER TABLE trading.emsys_telemetry
    ADD COLUMN IF NOT EXISTS soc_percent double precision,
    ADD COLUMN IF NOT EXISTS degradation_cost_eur double precision,
    ADD COLUMN IF NOT EXISTS availability_status boolean;

UPDATE trading.emsys_telemetry t
SET availability_status = (t.turbine_status NOT IN ('UNAVAILABLE', 'OFFLINE'))
WHERE t.availability_status IS NULL;

CREATE INDEX IF NOT EXISTS emsys_telemetry_asset_ts_idx
    ON trading.emsys_telemetry (asset_id, event_ts);

CREATE TABLE IF NOT EXISTS trading.down_regulation_events (
    event_id              varchar(50) PRIMARY KEY,
    asset_id              varchar(50) NOT NULL,
    portfolio_id          varchar(50),
    interval_start        timestamp NOT NULL,
    interval_end          timestamp NOT NULL,
    commanded_setpoint_kw double precision NOT NULL,
    reason                varchar(100),
    market_code           varchar(50) NOT NULL DEFAULT 'ELERING_mFRR_DOWN',
    event_ts              timestamp NOT NULL,
    source_system         varchar(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS trading.afrr_activations (
    activation_id   bigserial PRIMARY KEY,
    portfolio_id    varchar(50) NOT NULL,
    asset_id        varchar(50),
    event_ts        timestamp NOT NULL,
    setpoint_kw     double precision NOT NULL,
    direction       varchar(10) NOT NULL,
    price_eur_mwh   double precision,
    source_system   varchar(50) NOT NULL
);

CREATE INDEX IF NOT EXISTS afrr_activations_ts_idx
    ON trading.afrr_activations (event_ts);

CREATE TABLE IF NOT EXISTS trading.mfrr_activations (
    activation_id   varchar(50) PRIMARY KEY,
    portfolio_id    varchar(50) NOT NULL,
    market_code     varchar(50) NOT NULL,
    interval_start  timestamp NOT NULL,
    interval_end    timestamp NOT NULL,
    volume_mw       double precision NOT NULL,
    price_eur_mwh   double precision NOT NULL,
    activation_type varchar(20) NOT NULL,
    source_system   varchar(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS trading.sim_clock (
    clock_id     smallint PRIMARY KEY DEFAULT 1 CHECK (clock_id = 1),
    running      boolean NOT NULL DEFAULT false,
    sim_ts       timestamp NOT NULL,
    speed_factor double precision NOT NULL DEFAULT 60,
    updated_at   timestamp NOT NULL DEFAULT now()
);

INSERT INTO trading.sim_clock (clock_id, running, sim_ts, speed_factor)
VALUES (1, false, timestamp '2026-06-02 12:00:00', 60)
ON CONFLICT (clock_id) DO NOTHING;
