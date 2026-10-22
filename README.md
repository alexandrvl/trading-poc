# Tradic PoC

Interactive electricity-trading proof of concept on **PostgreSQL**. Mocked Emsys-like VPP, Meteologica-like forecast ensembles and a thin Periotheus-like ETRM write into the existing `trading` schema. dbt Data Vault models run against Postgres so reports update after a simulated down-regulation.

The original Trino / Iceberg / Superset lakehouse stack is unchanged under `trading-dbt/`. Do not run both compose files at once — they share host port **5433**.

## Quick start (interactive)

```bash
docker compose -f docker-compose.interactive.yml up --build
```

| Service | URL | Notes |
| --- | --- | --- |
| Streamlit UI | http://localhost:8501 | Drive the sim and inspect reports |
| FastAPI | http://localhost:8000/docs | REST + WebSocket `/ws` |
| PostgreSQL | localhost:5433 | `dbt_user` / `dbt_password`, database `iceberg_dbt` |

1. Click **Start** in the sidebar (sim clock begins 2026-06-02 12:00, 60 sim minutes per wall second).
2. Select `WT-EE-N-01` and click **Send down-regulation**.
3. Wait until the 15-minute ISP closes (~15 wall seconds at default speed).
4. Open report **mart_curtailment_compensation** and click **Refresh reports (dbt run)**.
5. You should see lost energy and mFRR-down compensation for the curtailed asset.

## What was added

- Postgres extensions in `trading-dbt/init-scripts/03-interactive.sql` (telemetry SoC / availability, down-regulation and aFRR/mFRR event tables, sim clock). Existing landing tables are kept.
- dbt **postgres** target. Macros are dialect-aware so the same Data Vault models still run on Trino.
- New sources/staging for `down_regulation_events`, `afrr_activations`, `mfrr_activations`, plus `sat_asset_down_regulation`.
- FastAPI simulators in `interactive/backend` and Streamlit UI in `interactive/ui`.

## Local run without Docker (Postgres already on 5433)

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r interactive/requirements.txt
export PYTHONPATH=.
export PGHOST=localhost PGPORT=5433 PGUSER=dbt_user PGPASSWORD=dbt_password PGDATABASE=iceberg_dbt
uvicorn interactive.backend.main:app --host 0.0.0.0 --port 8000
# other terminal
TRADING_API_URL=http://localhost:8000 streamlit run interactive/ui/streamlit_app.py --server.address 0.0.0.0
```

Unit tests (no database):

```bash
PYTHONPATH=. pytest interactive/tests
```

## Lakehouse path

See [trading-dbt/README.md](trading-dbt/README.md) for Trino, MinIO, Iceberg and Superset.
