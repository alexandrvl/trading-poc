# Electricity trading Data Vault

dbt project for asset-level electricity billing. The original stack is Trino and Apache Iceberg. The **interactive PoC** runs the same models on PostgreSQL and also starts MinIO + Trino for live Iceberg append — from the repo root: `docker compose -f docker-compose.interactive.yml up --build` (see the root README). Do not run this lakehouse compose and the interactive compose at the same time; both bind Postgres to host port 5433.

Portfolio trades from Periotheus are split onto Emsys assets, with Meteologica forecasts used for imbalance attribution and curtailment.

The loader and local stack follow [iceberg-dbt-etl](https://github.com/alexandrvl/iceberg-dbt-etl).

## Quick start

```bash
docker compose up -d
docker compose logs -f dbt-models
```

| Service | Host | Credentials |
| --- | --- | --- |
| Trino | localhost:8082 | none |
| MinIO console | http://localhost:9011 | minio_user / minio_password |
| PostgreSQL | localhost:5433 | dbt_user / dbt_password, database iceberg_dbt |
| Superset | http://localhost:8088 | admin / admin |

Superset starts with the rest of the stack. The first boot installs the metadata schema and publishes the **Asset internal billing** dashboard at `/superset/dashboard/asset-internal-billing/`. Chart data is a live query (`cache_timeout` `-1`); the dashboard auto-refreshes every 60 seconds. The lakehouse compose reads the marts through Trino (`trino://trino@trino:8080/iceberg`); the interactive compose points the same dashboard at Postgres `information_mart`. Give dbt a few minutes on a cold start; Superset retries the marts for about ten minutes. The dashboard is recreated on each Superset start, so keep layout changes in `superset/bootstrap_bi.py`.

```bash
docker exec -it trading-dbt-trino trino --execute "SELECT asset_id, portfolio_id, interval_start, allocated_revenue_eur, imbalance_cost_eur, net_revenue_eur FROM iceberg.information_mart.mart_asset_internal_billing WHERE interval_start = timestamp '2026-06-01 12:00:00' ORDER BY portfolio_id, asset_id"
```

Clean restart:

```bash
docker compose down -v
docker compose up -d
```

Re-running dbt is safe. Re-running the loader appends another copy of the raw files, so do that only after `docker compose down -v`.

## What the sample afternoon shows

Telemetry is one-minute data for 2026-06-01 12:00–14:00.

- `Wind_EE_North` sells energy as a portfolio. At 12:00, `WT-EE-N-02` is below its P50 forecast and takes the whole imbalance charge. `WT-EE-N-12` is above forecast and is not charged.
- `WT-EE-N-01` follows an aFRR setpoint at 12:30 and is curtailed by external control from 13:00 to 13:30. Lost energy uses the intraday forecast and the mFRR down price.
- `WT-EE-N-12` belonged to `Solar_EE_South` until 2026-05-01. June billing uses `Wind_EE_North` only.
- Meteologica sends P10, P50 and P90 for the same asset and run. A later P90 revision is kept in the raw satellite and becomes the current baseline. Billing still uses the forecast that existed at the interval.

## Layers

| Layer | Schema | Contents |
| --- | --- | --- |
| Landing | `iceberg.raw` | Assets, portfolios, orders, telemetry, forecasts, settlements |
| Staging | `iceberg.staging` | Hash keys, hash diffs, `ldts`, `rsrc` |
| Raw vault | `iceberg.raw_vault` | Hubs, links, satellites, reference tables |
| Business vault | `iceberg.business_vault` | PIT, bridge, allocation, imbalance, reserves, curtailment |
| Marts | `iceberg.information_mart` | Asset bill, curtailment, portfolio reconciliation |

Hubs: `hub_asset`, `hub_portfolio`, `hub_market`, `hub_trade_order`.

Links: `link_portfolio_asset`, `link_order_portfolio`, `link_order_market`.

Satellites: asset details, append-only Emsys telemetry, capacity status, multi-active Meteologica forecast, portfolio details, Periotheus order, portfolio-asset effectivity.

`sat_asset_meteologica_forecast` is a multi-active satellite. The primary key is asset hash, load timestamp, ensemble `type_code` and target time. A hash diff suppresses an unchanged republish.

## Billing rules

Wholesale revenue for interval `t`:

```text
allocated(a) = portfolio_revenue * generation(a) / sum(generation)
```

Imbalance is shared only with assets whose forecast error has the same sign as the portfolio error:

```text
weight(a) = max(0, sign(portfolio_delta) * delta(a))
imbalance(a) = portfolio_imbalance * weight(a) / sum(weight)
```

`delta(a)` is measured generation minus the P50 forecast available at the start of the interval.

Balancing cash:

- aFRR and mFRR readiness, and capacity-market availability, follow declared megawatts
- aFRR energy follows minutes in `AFRR` control
- FCR follows autonomous response, then declared availability when nobody responded
- capacity penalties follow megawatts declared unavailable

Curtailment starts when control mode is `EXTERNAL_CONTROL` and the setpoint is below nominal power. Lost energy is the positive gap versus the intraday downscale, priced at `ELERING_mFRR_DOWN`.

Net revenue is wholesale allocation, minus imbalance and capacity penalties, plus reserve revenue and curtailment compensation.

## Materializations

| Model | Strategy | Why |
| --- | --- | --- |
| `sat_asset_emsys_telemetry` | append, partitioned by `day(ldts)` | Insert-only telemetry. Trino Iceberg uses the `partitioning` table property. |
| Other raw satellites | merge on the satellite key | Insert a row only when the hash diff changed |
| `bv_forecast_baseline` | delete+insert | Replace a target when the forecast is republished |
| `bv_asset_net_revenue` | merge on asset, portfolio and interval | Correct a price without duplicating the bill |

`bv_asset_net_revenue` and `bv_forecast_baseline` compare upstream `ldts` with `source_ldts`. When nothing new has landed, they return no rows.

Point-in-time rows in `pit_asset` turn satellite history into equi-joins in `bv_asset_interval`.

## dbt commands

The `trading/` directory is mounted into the dbt container, so SQL changes do not need an image rebuild.

```bash
docker compose run --rm dbt-models bash
dbt run --select staging raw_vault business_vault information_mart --profiles-dir /app/trading
dbt test --profiles-dir /app/trading
```

From the host, with Trino already on port 8082:

```bash
cd trading
dbt run --select staging raw_vault business_vault information_mart
```

Against the interactive Postgres (host port 5433):

```bash
cd trading
DBT_TARGET=postgres dbt run --select staging raw_vault business_vault information_mart --target postgres \
  --vars '{raw_database: iceberg_dbt, raw_schema: trading, trino_table_type: ""}'
```

## Project layout

```text
init-scripts/          PostgreSQL source schema and the sample afternoon
load_data_generic.py   PostgreSQL to Iceberg loader
trading/models/        staging, raw vault, business vault, marts
trading/tests/         allocation, imbalance, curtailment and forecast tests
trino/etc/             Iceberg catalog on PostgreSQL and MinIO
superset/              Superset image, Trino connection, billing dashboard
```
