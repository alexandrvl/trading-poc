from __future__ import annotations

import asyncio
import logging
import math
import os
import random
import subprocess
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from interactive.backend.config import SIM_RAW, settings
from interactive.backend.db import db
from interactive.backend.iceberg_ingest import IcebergSink
from interactive.backend.sim.clock import SimClock, quarter_hour_start
from interactive.backend.sim.etrm import (
    balancing_rows,
    da_order_row,
    down_regulation_event,
    price_rows,
    sample_da_price,
    settlement_rows,
)
from interactive.backend.sim.forecasts import build_forecast_rows
from interactive.backend.sim.vpp import AssetRuntime, seed_assets
from interactive.backend.ws import ConnectionManager

logger = logging.getLogger(__name__)

TELEMETRY_INSERT = """
INSERT INTO trading.emsys_telemetry (
    asset_id, event_ts, active_power_kw, reactive_power_kvar,
    turbine_status, setpoint_limit_kw, control_mode, source_system, ingested_at,
    soc_percent, degradation_cost_eur, availability_status, soh_percent
) VALUES (%s, %s, %s, %s, %s, %s, %s, 'EMSYS_VPP', %s, %s, %s, %s, %s)
"""

FORECAST_UPSERT = """
INSERT INTO trading.meteologica_forecast (
    asset_id, forecast_run_ts, type_code, target_timestamp,
    expected_power_kw, wind_speed_m_s, ghi_w_m2, source_system
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (asset_id, forecast_run_ts, type_code, target_timestamp)
DO UPDATE SET expected_power_kw = EXCLUDED.expected_power_kw
"""

CAPACITY_UPSERT = """
INSERT INTO trading.capacity_status (
    asset_id, status_ts, declared_availability_mw, outage_status, derating_factor, source_system
) VALUES (%s, %s, %s, %s, %s, 'EMSYS_VPP')
ON CONFLICT (asset_id, status_ts) DO UPDATE SET
    declared_availability_mw = EXCLUDED.declared_availability_mw,
    outage_status = EXCLUDED.outage_status,
    derating_factor = EXCLUDED.derating_factor
"""

ORDER_UPSERT = """
INSERT INTO trading.trade_orders (
    order_id, portfolio_id, market_code, price_eur, volume_mw, delivery_start,
    delivery_end, order_type, direction, order_status, trade_ts, source_system
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (order_id) DO UPDATE SET
    order_status = EXCLUDED.order_status,
    price_eur = EXCLUDED.price_eur,
    volume_mw = EXCLUDED.volume_mw
"""

SETTLEMENT_UPSERT = """
INSERT INTO trading.portfolio_settlement (
    portfolio_id, market_code, interval_start, interval_end, revenue_eur,
    volume_mwh, imbalance_cost_eur, clearing_price_eur_mwh, loaded_at, source_system
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (portfolio_id, market_code, interval_start) DO UPDATE SET
    revenue_eur = EXCLUDED.revenue_eur,
    volume_mwh = EXCLUDED.volume_mwh,
    imbalance_cost_eur = EXCLUDED.imbalance_cost_eur,
    clearing_price_eur_mwh = EXCLUDED.clearing_price_eur_mwh,
    loaded_at = EXCLUDED.loaded_at
"""

BALANCING_UPSERT = """
INSERT INTO trading.balancing_settlement (
    portfolio_id, market_code, interval_start, interval_end,
    capacity_revenue_eur, energy_revenue_eur, penalty_eur, loaded_at, source_system
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (portfolio_id, market_code, interval_start) DO UPDATE SET
    capacity_revenue_eur = EXCLUDED.capacity_revenue_eur,
    energy_revenue_eur = EXCLUDED.energy_revenue_eur,
    penalty_eur = EXCLUDED.penalty_eur,
    loaded_at = EXCLUDED.loaded_at
"""

PRICE_UPSERT = """
INSERT INTO trading.market_prices (
    market_code, interval_start, interval_end, clearing_price_eur_mwh, loaded_at, source_system
) VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (market_code, interval_start) DO UPDATE SET
    clearing_price_eur_mwh = EXCLUDED.clearing_price_eur_mwh,
    loaded_at = EXCLUDED.loaded_at
"""

AFRR_INSERT = """
INSERT INTO trading.afrr_activations (
    portfolio_id, asset_id, event_ts, setpoint_kw, direction,
    price_eur_mwh, source_system
) VALUES (%s, %s, %s, %s, %s, %s, 'PERIOTHEUS')
"""

REPORTS = {
    "mart_curtailment_compensation": "information_mart.mart_curtailment_compensation",
    "mart_asset_internal_billing": "information_mart.mart_asset_internal_billing",
    "mart_portfolio_reconciliation": "information_mart.mart_portfolio_reconciliation",
    "bv_down_regulation": "business_vault.bv_down_regulation",
    "bv_pro_rata_allocation": "business_vault.bv_pro_rata_allocation",
}


class SimEngine:
    def __init__(self, hub: ConnectionManager) -> None:
        self.hub = hub
        self.clock = SimClock(
            sim_ts=datetime.fromisoformat(settings.sim_start),
            speed_factor=settings.default_speed_factor,
        )
        self.assets: dict[str, AssetRuntime] = {}
        self.membership: dict[str, str] = {}
        self.buffer: list[tuple] = []
        self.isp_samples: dict[tuple[str, datetime], list[dict]] = defaultdict(list)
        self.last_samples: dict[str, dict] = {}
        self.last_prices: dict[str, float] = {
            "NP_DA_EE": settings.da_price_eur_mwh,
            "ELERING_mFRR_DOWN": settings.mfrr_down_price_eur_mwh,
        }
        self._task: asyncio.Task | None = None
        self._afrr_task: asyncio.Task | None = None
        self._iceberg_task: asyncio.Task | None = None
        self._dbt_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._dbt_lock = asyncio.Lock()
        self.last_dbt: dict[str, Any] = {"status": "never"}
        self.events: list[dict] = []
        self.recent_afrr: deque[dict] = deque(maxlen=80)
        self.rng = random.Random(settings.rng_seed)
        self.iceberg = IcebergSink(settings)

    async def load(self) -> None:
        asset_rows = await db.fetch(
            """
            SELECT asset_id, technology, nominal_power_kw, latitude, longitude
            FROM trading.assets
            ORDER BY asset_id
            """
        )
        self.assets = seed_assets(asset_rows, rng_seed=settings.rng_seed)
        members = await db.fetch(
            """
            SELECT asset_id, portfolio_id
            FROM trading.portfolio_membership
            WHERE valid_to IS NULL
            """
        )
        self.membership = {m["asset_id"]: m["portfolio_id"] for m in members}
        clock_row = await db.fetchone("SELECT running, sim_ts, speed_factor FROM trading.sim_clock WHERE clock_id = 1")
        if clock_row:
            self.clock.sim_ts = clock_row["sim_ts"]
            self.clock.speed_factor = float(clock_row["speed_factor"])
            self.clock.running = False
        await self.publish_forecasts(self.clock.sim_ts - timedelta(hours=6))
        await self._seed_da_orders()
        await self._persist_clock()

    def ensure_jobs(self) -> None:
        if self._iceberg_task is None or self._iceberg_task.done():
            self._iceberg_task = asyncio.create_task(self._iceberg_loop(), name="iceberg")
        if self._dbt_task is None or self._dbt_task.done():
            self._dbt_task = asyncio.create_task(self._dbt_loop(), name="dbt")

    async def start(self) -> dict:
        self.clock.running = True
        await self._persist_clock()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop(), name="sim-clock")
        if self._afrr_task is None or self._afrr_task.done():
            self._afrr_task = asyncio.create_task(self._afrr_loop(), name="afrr")
        self.ensure_jobs()
        return self.snapshot()

    async def pause(self) -> dict:
        self.clock.running = False
        await self._persist_clock()
        return self.snapshot()

    def snapshot(self) -> dict:
        last_afrr = self.recent_afrr[-1] if self.recent_afrr else None
        return {
            "running": self.clock.running,
            "sim_ts": self.clock.sim_ts.isoformat(sep=" "),
            "speed_factor": self.clock.speed_factor,
            "isp_start": quarter_hour_start(self.clock.sim_ts).isoformat(sep=" "),
            "afrr_period_seconds": settings.afrr_period_seconds,
            "last_afrr": last_afrr,
            "dbt_run_every_minutes": settings.dbt_run_every_minutes,
            "iceberg_flush_seconds": settings.iceberg_flush_seconds,
            "iceberg": self.iceberg.last_flush,
            "assets": [
                {
                    "asset_id": a.asset_id,
                    "technology": a.technology,
                    "nominal_kw": a.nominal_kw,
                    "available": a.available,
                    "setpoint_limit_kw": a.setpoint_limit_kw,
                    "control_mode": a.control_mode,
                    "soc_percent": a.soc_percent if a.technology.upper() == "BESS" else None,
                    "soh_percent": a.rainflow.soh_percent if a.rainflow else None,
                    "degradation_cost_eur": a.rainflow.cumulative_cost_eur if a.rainflow else None,
                    "last_power_kw": a.last_power_kw,
                    "portfolio_id": self.membership.get(a.asset_id),
                }
                for a in self.assets.values()
            ],
            "last_prices": self.last_prices,
            "last_dbt": self.last_dbt,
            "recent_events": self.events[-12:],
        }

    async def set_speed(self, speed_factor: float) -> dict:
        self.clock.speed_factor = max(1.0, float(speed_factor))
        await self._persist_clock()
        return self.snapshot()

    async def set_availability(self, asset_id: str, available: bool) -> dict:
        asset = self._asset(asset_id)
        asset.available = available
        status = "AVAILABLE" if available else "UNAVAILABLE"
        factor = 1.0 if available else 0.0
        declared = (asset.nominal_kw / 1000.0) * factor
        await db.execute(
            CAPACITY_UPSERT,
            (asset_id, self.clock.sim_ts, declared, status, factor),
        )
        self._note(f"{asset_id} availability={available}")
        return self.snapshot()

    async def set_setpoint(self, asset_id: str, setpoint_limit_kw: float) -> dict:
        asset = self._asset(asset_id)
        asset.setpoint_limit_kw = float(setpoint_limit_kw)
        self._note(f"{asset_id} setpoint={setpoint_limit_kw} kW")
        return self.snapshot()

    async def down_regulate(
        self,
        asset_id: str,
        setpoint_limit_kw: float | None = None,
        duration_minutes: int = 20,
    ) -> dict:
        asset = self._asset(asset_id)
        limit = setpoint_limit_kw if setpoint_limit_kw is not None else asset.nominal_kw * 0.2
        asset.control_mode = "EXTERNAL_CONTROL"
        asset.setpoint_limit_kw = float(limit)
        asset.down_reg_until = self.clock.sim_ts + timedelta(minutes=duration_minutes)
        portfolio_id = self.membership.get(asset_id, "Wind_EE_North")
        event = down_regulation_event(
            asset_id, portfolio_id, self.clock.sim_ts, duration_minutes, limit
        )
        await db.execute(
            """
            INSERT INTO trading.down_regulation_events (
                event_id, asset_id, portfolio_id, interval_start, interval_end,
                commanded_setpoint_kw, reason, market_code, event_ts, source_system
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_id) DO NOTHING
            """,
            event,
        )
        await db.execute(
            """
            INSERT INTO trading.mfrr_activations (
                activation_id, portfolio_id, market_code, interval_start, interval_end,
                volume_mw, price_eur_mwh, activation_type, source_system
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (activation_id) DO NOTHING
            """,
            (
                f"MFRR-{event[0]}",
                portfolio_id,
                "ELERING_mFRR_DOWN",
                event[3],
                event[4],
                max(0.1, (asset.nominal_kw - limit) / 1000.0),
                settings.mfrr_down_price_eur_mwh,
                "DIRECT",
                "PERIOTHEUS",
            ),
        )
        await db.execute(
            ORDER_UPSERT,
            (
                f"ORD-MFRR-{event[0]}",
                portfolio_id,
                "ELERING_mFRR_DOWN",
                settings.mfrr_down_price_eur_mwh,
                max(0.1, (asset.nominal_kw - limit) / 1000.0),
                event[3],
                event[4],
                "SINGLE",
                "SELL",
                "CONFIRMED",
                self.clock.sim_ts,
                "PERIOTHEUS",
            ),
        )
        self._note(
            f"Down-regulation {asset_id} to {limit:.0f} kW until {asset.down_reg_until}"
        )
        return {"event_id": event[0], **self.snapshot()}

    async def place_bid(
        self,
        portfolio_id: str,
        market_code: str,
        price_eur: float,
        volume_mw: float,
        direction: str = "SELL",
        accept: bool = True,
    ) -> dict:
        isp = int(SIM_RAW["clock"]["isp_minutes"])
        start = quarter_hour_start(self.clock.sim_ts)
        end = start + timedelta(minutes=isp)
        order_id = f"ORD-BID-{uuid4().hex[:10]}"
        status = "CONFIRMED" if accept else "OPEN"
        floor = None
        if accept and "mFRR" in market_code:
            for asset in self.assets.values():
                if self.membership.get(asset.asset_id) != portfolio_id:
                    continue
                if asset.technology.upper() != "BESS":
                    continue
                floor = asset.mfrr_floor_eur_mwh(volume_mw, duration_h=isp / 60.0)
                if price_eur < floor:
                    status = "REJECTED"
                    accept = False
                    self._note(
                        f"Rainflow rejected {market_code} {volume_mw} MW @ {price_eur:.2f} "
                        f"(floor {floor:.2f} EUR/MWh, SoH {asset.rainflow.soh_percent:.3f}%)"
                    )
                elif price_eur < floor * 1.05:
                    price_eur = round(floor * 1.05, 2)
                    status = "REPRICED"
                    self._note(f"Rainflow repriced {order_id} to {price_eur} EUR/MWh")
                break
        if accept and market_code.startswith("ELERING_aFRR"):
            for asset in self.assets.values():
                if self.membership.get(asset.asset_id) == portfolio_id and asset.technology.upper() == "BESS":
                    asset.control_mode = "AFRR"
                    asset.setpoint_limit_kw = volume_mw * 1000.0
        await db.execute(
            ORDER_UPSERT,
            (
                order_id,
                portfolio_id,
                market_code,
                price_eur,
                volume_mw,
                start,
                end,
                "SINGLE",
                direction,
                status,
                self.clock.sim_ts,
                "PERIOTHEUS",
            ),
        )
        if status == "CONFIRMED":
            self._note(f"Bid {order_id} {status} {volume_mw} MW @ {price_eur} on {market_code}")
        return {
            "order_id": order_id,
            "order_status": status,
            "price_eur": price_eur,
            "wear_floor_eur_mwh": floor,
            **self.snapshot(),
        }

    async def publish_forecasts(self, run_ts: datetime | None = None) -> int:
        run_ts = run_ts or (self.clock.sim_ts - timedelta(minutes=30))
        rows = build_forecast_rows(
            self.assets, run_ts, self.clock.sim_ts, settings.forecast_horizon_hours
        )
        await db.executemany(FORECAST_UPSERT, rows)
        self._note(f"Forecast run {run_ts} ({len(rows)} rows)")
        return len(rows)

    async def run_dbt(self, full_refresh: bool = False) -> dict:
        async with self._dbt_lock:
            project = Path(settings.dbt_project_dir)
            if not (project / "dbt_project.yml").exists():
                local = Path(__file__).resolve().parents[3] / "trading-dbt" / "trading"
                if (local / "dbt_project.yml").exists():
                    project = local
            cmd = [
                "dbt",
                "run",
                "--select",
                "staging raw_vault business_vault information_mart",
                "--profiles-dir",
                str(project),
                "--project-dir",
                str(project),
                "--target",
                "postgres",
                "--vars",
                '{"raw_database": "iceberg_dbt", "raw_schema": "trading", "trino_table_type": ""}',
            ]
            if full_refresh:
                cmd.append("--full-refresh")
            env = os.environ.copy()
            env.update(
                {
                    "DBT_TARGET": "postgres",
                    "DBT_POSTGRES_HOST": settings.pghost,
                    "DBT_POSTGRES_PORT": str(settings.pgport),
                    "DBT_POSTGRES_USER": settings.pguser,
                    "DBT_POSTGRES_PASSWORD": settings.pgpassword,
                    "DBT_POSTGRES_DB": settings.pgdatabase,
                }
            )
            started = datetime.now(timezone.utc).replace(tzinfo=None)
            proc = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(project),
            )
            self.last_dbt = {
                "status": "ok" if proc.returncode == 0 else "error",
                "returncode": proc.returncode,
                "started_at": started.isoformat(),
                "duration_s": round(
                    (datetime.now(timezone.utc).replace(tzinfo=None) - started).total_seconds(), 2
                ),
                "stdout_tail": (proc.stdout or "")[-4000:],
                "stderr_tail": (proc.stderr or "")[-2000:],
            }
            self._note(f"dbt run {self.last_dbt['status']} in {self.last_dbt['duration_s']}s")
            return self.last_dbt

    async def report_rows(self, name: str, limit: int = 200) -> list[dict]:
        if name not in REPORTS:
            raise KeyError(name)
        table = REPORTS[name]
        return await db.fetch(
            f"SELECT * FROM {table} ORDER BY interval_start DESC LIMIT %s",
            (limit,),
        )

    async def telemetry_history(self, minutes: int = 90) -> list[dict]:
        return await db.fetch(
            """
            SELECT asset_id, event_ts, active_power_kw, setpoint_limit_kw,
                   control_mode, soc_percent, availability_status, soh_percent,
                   degradation_cost_eur
            FROM trading.emsys_telemetry
            WHERE event_ts >= %s
            ORDER BY event_ts DESC
            LIMIT 2000
            """,
            (self.clock.sim_ts - timedelta(minutes=minutes),),
        )

    async def _run_loop(self) -> None:
        while True:
            if not self.clock.running:
                await asyncio.sleep(0.2)
                continue
            try:
                await self._tick()
            except Exception:
                logger.exception("sim tick failed")
            await asyncio.sleep(self.clock.wall_sleep_seconds())

    async def _afrr_loop(self) -> None:
        while True:
            if self.clock.running:
                try:
                    await self._picasso_tick()
                except Exception:
                    logger.exception("picasso tick failed")
            await asyncio.sleep(settings.afrr_period_seconds)

    async def _iceberg_loop(self) -> None:
        interval = max(1.0, float(settings.iceberg_flush_seconds))
        while True:
            await asyncio.sleep(min(2.0, interval))
            if self.iceberg.should_flush():
                try:
                    await asyncio.to_thread(self.iceberg.flush)
                except Exception:
                    logger.exception("iceberg flush loop failed")

    async def _dbt_loop(self) -> None:
        interval = max(1.0, float(settings.dbt_run_every_minutes) * 60.0)
        while True:
            await asyncio.sleep(interval)
            try:
                await self.run_dbt(full_refresh=False)
            except Exception:
                logger.exception("scheduled dbt run failed")

    async def _picasso_tick(self) -> None:
        phase = time.time()
        frac = float(SIM_RAW["markets"]["afrr_setpoint_frac"])
        rows = []
        for asset in self.assets.values():
            if asset.technology.upper() != "BESS":
                continue
            if asset.control_mode == "EXTERNAL_CONTROL":
                continue
            asset.control_mode = "AFRR"
            asset.setpoint_limit_kw = asset.nominal_kw * frac * math.sin(phase / 8.0)
            direction = "UP" if asset.setpoint_limit_kw >= 0 else "DOWN"
            payload = (
                self.membership.get(asset.asset_id, "Wind_EE_North"),
                asset.asset_id,
                self.clock.sim_ts,
                asset.setpoint_limit_kw,
                direction,
                settings.afrr_price_eur_mwh,
            )
            await db.execute(AFRR_INSERT, payload)
            row = {
                "portfolio_id": payload[0],
                "asset_id": asset.asset_id,
                "event_ts": self.clock.sim_ts,
                "setpoint_kw": asset.setpoint_limit_kw,
                "direction": direction,
                "price_eur_mwh": settings.afrr_price_eur_mwh,
                "source_system": "PERIOTHEUS",
                "wall_ts": datetime.now(timezone.utc).isoformat(),
            }
            rows.append(row)
            self.recent_afrr.append(row)
        if rows:
            self.iceberg.enqueue_afrr(rows)
            self.hub.publish({"type": "afrr", "period_s": settings.afrr_period_seconds, "rows": rows})

    async def _tick(self) -> None:
        async with self._lock:
            ts = self.clock.sim_ts
            prev_isp = quarter_hour_start(ts)
            samples = [asset.step(ts) for asset in self.assets.values()]
            ingested = datetime.now(timezone.utc).replace(tzinfo=None)
            iceberg_rows = []
            for sample in samples:
                self.last_samples[sample["asset_id"]] = sample
                isp = quarter_hour_start(sample["event_ts"])
                self.isp_samples[(sample["asset_id"], isp)].append(sample)
                self.buffer.append(
                    (
                        sample["asset_id"],
                        sample["event_ts"],
                        sample["active_power_kw"],
                        sample["reactive_power_kvar"],
                        sample["turbine_status"],
                        sample["setpoint_limit_kw"],
                        sample["control_mode"],
                        ingested,
                        sample["soc_percent"],
                        sample["degradation_cost_eur"],
                        sample["availability_status"],
                        sample.get("soh_percent"),
                    )
                )
                iceberg_rows.append(
                    {
                        "asset_id": sample["asset_id"],
                        "event_ts": sample["event_ts"],
                        "active_power_kw": sample["active_power_kw"],
                        "reactive_power_kvar": sample["reactive_power_kvar"],
                        "turbine_status": sample["turbine_status"],
                        "setpoint_limit_kw": sample["setpoint_limit_kw"],
                        "control_mode": sample["control_mode"],
                        "source_system": "EMSYS_VPP",
                        "ingested_at": ingested,
                    }
                )
            self.iceberg.enqueue_telemetry(iceberg_rows)
            await self._flush()
            self.clock.step_minutes()
            new_isp = quarter_hour_start(self.clock.sim_ts)
            if new_isp != prev_isp:
                await self._settle_isp(prev_isp)
                if self.clock.sim_ts.hour % 6 == 0 and self.clock.sim_ts.minute == 0:
                    await self.publish_forecasts(self.clock.sim_ts - timedelta(minutes=30))
            self.hub.publish(
                {
                    "type": "telemetry",
                    "sim_ts": ts.isoformat(sep=" "),
                    "prices": self.last_prices,
                    "samples": [
                        {
                            "asset_id": s["asset_id"],
                            "active_power_kw": s["active_power_kw"],
                            "setpoint_limit_kw": s["setpoint_limit_kw"],
                            "control_mode": s["control_mode"],
                            "soc_percent": s["soc_percent"],
                            "soh_percent": s.get("soh_percent"),
                            "availability_status": s["availability_status"],
                        }
                        for s in samples
                    ],
                }
            )
            await self._persist_clock()

    async def _flush(self) -> None:
        if not self.buffer:
            return
        batch = self.buffer
        self.buffer = []
        await db.executemany(TELEMETRY_INSERT, batch)

    async def _settle_isp(self, interval_start: datetime) -> None:
        loaded_at = self.clock.sim_ts
        p50_rows = await db.fetch(
            """
            SELECT asset_id, expected_power_kw
            FROM trading.meteologica_forecast
            WHERE type_code = 'Ensemble_P50'
              AND target_timestamp = %s
            ORDER BY forecast_run_ts DESC
            """,
            (interval_start,),
        )
        p50 = {}
        for row in p50_rows:
            p50.setdefault(row["asset_id"], float(row["expected_power_kw"]))

        by_portfolio: dict[str, dict[str, float]] = defaultdict(
            lambda: {"generation_mwh": 0.0, "forecast_mwh": 0.0, "afrr": 0.0, "mfrr": 0.0, "available": 1.0}
        )
        curtailed = False
        isp_h = int(SIM_RAW["clock"]["isp_minutes"]) / 60.0
        for asset_id, asset in self.assets.items():
            samples = self.isp_samples.pop((asset_id, interval_start), [])
            if not samples:
                continue
            avg_kw = sum(s["active_power_kw"] for s in samples) / len(samples)
            gen_mwh = avg_kw * isp_h / 1000.0
            fc_mwh = p50.get(asset_id, 0.0) * isp_h / 1000.0
            portfolio_id = self.membership.get(asset_id, "Wind_EE_North")
            bucket = by_portfolio[portfolio_id]
            bucket["generation_mwh"] += gen_mwh
            bucket["forecast_mwh"] += fc_mwh
            if any(s["control_mode"] == "AFRR" for s in samples):
                bucket["afrr"] += settings.afrr_price_eur_mwh * 0.3
            if any(s["control_mode"] == "EXTERNAL_CONTROL" for s in samples):
                bucket["mfrr"] += 8.0
                curtailed = True
            if not asset.available:
                bucket["available"] = 0.0

        da_price = sample_da_price(self.rng)
        mfrr_price = settings.mfrr_down_price_eur_mwh if curtailed else max(20.0, da_price * 0.5)
        self.last_prices = {
            "NP_DA_EE": da_price,
            "ELERING_mFRR_DOWN": mfrr_price,
        }
        await db.executemany(
            PRICE_UPSERT,
            price_rows(interval_start, da_price, mfrr_price, loaded_at),
        )
        for portfolio_id, bucket in by_portfolio.items():
            await db.executemany(
                SETTLEMENT_UPSERT,
                settlement_rows(
                    portfolio_id,
                    interval_start,
                    bucket["generation_mwh"],
                    bucket["forecast_mwh"],
                    da_price,
                    settings.imbalance_price_eur_mwh,
                    loaded_at,
                ),
            )
            await db.executemany(
                BALANCING_UPSERT,
                balancing_rows(
                    portfolio_id,
                    interval_start,
                    bool(bucket["available"]),
                    bucket["afrr"],
                    bucket["mfrr"],
                    settings.bbcm_fee_eur if portfolio_id == "Wind_EE_North" else 0.0,
                    loaded_at,
                ),
            )
        self._note(f"Settled ISP {interval_start}" + (" (curtailed)" if curtailed else ""))

    async def _seed_da_orders(self) -> None:
        start = quarter_hour_start(self.clock.sim_ts)
        end = start + timedelta(hours=6)
        wind_mw = sum(
            a.nominal_kw for a in self.assets.values()
            if self.membership.get(a.asset_id) == "Wind_EE_North" and a.technology.upper() != "BESS"
        ) / 1000.0 * 0.6
        solar_mw = sum(
            a.nominal_kw for a in self.assets.values()
            if self.membership.get(a.asset_id) == "Solar_EE_South"
        ) / 1000.0 * 0.5
        da_price = sample_da_price(self.rng)
        await db.execute(
            ORDER_UPSERT,
            da_order_row(
                "Wind_EE_North", start, end, round(wind_mw, 3),
                da_price, start - timedelta(hours=20),
            ),
        )
        await db.execute(
            ORDER_UPSERT,
            da_order_row(
                "Solar_EE_South", start, end, round(solar_mw, 3),
                da_price, start - timedelta(hours=20),
            ),
        )

    async def _persist_clock(self) -> None:
        await db.execute(
            """
            UPDATE trading.sim_clock
            SET running = %s, sim_ts = %s, speed_factor = %s, updated_at = now()
            WHERE clock_id = 1
            """,
            (self.clock.running, self.clock.sim_ts, self.clock.speed_factor),
        )

    def _asset(self, asset_id: str) -> AssetRuntime:
        if asset_id not in self.assets:
            raise KeyError(asset_id)
        return self.assets[asset_id]

    def _note(self, message: str) -> None:
        self.events.append({"ts": self.clock.sim_ts.isoformat(sep=" "), "message": message})
        logger.info(message)
