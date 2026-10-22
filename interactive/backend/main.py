from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from interactive.backend.config import settings
from interactive.backend.db import db
from interactive.backend.sim.engine import REPORTS, SimEngine
from interactive.backend.trino_client import trino_query
from interactive.backend.ws import ConnectionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

hub = ConnectionManager(maxsize=settings.ws_queue_size)
engine = SimEngine(hub)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.connect()
    await engine.load()
    logger.info("interactive backend ready at sim_ts=%s", engine.clock.sim_ts)
    try:
        yield
    finally:
        await engine.pause()
        await db.close()


app = FastAPI(title="Tradic interactive PoC", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SpeedBody(BaseModel):
    speed_factor: float = Field(ge=1, le=3600)


class AvailabilityBody(BaseModel):
    available: bool


class SetpointBody(BaseModel):
    setpoint_limit_kw: float = Field(ge=0)


class DownRegBody(BaseModel):
    asset_id: str = "WT-EE-N-01"
    setpoint_limit_kw: float | None = None
    duration_minutes: int = Field(default=20, ge=5, le=120)


class BidBody(BaseModel):
    portfolio_id: str = "Wind_EE_North"
    market_code: str = "NP_DA_EE"
    price_eur: float = 80.0
    volume_mw: float = Field(gt=0)
    direction: str = "SELL"
    accept: bool = True


class DbtBody(BaseModel):
    full_refresh: bool = False


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/state")
async def state() -> dict[str, Any]:
    return engine.snapshot()


@app.get("/telemetry/latest")
async def telemetry_latest() -> dict[str, Any]:
    snap = engine.snapshot()
    snap["samples"] = list(engine.last_samples.values())
    return snap


@app.get("/telemetry/history")
async def telemetry_history(minutes: int = 90) -> list[dict[str, Any]]:
    return await engine.telemetry_history(minutes)


@app.post("/sim/start")
async def sim_start() -> dict[str, Any]:
    return await engine.start()


@app.post("/sim/pause")
async def sim_pause() -> dict[str, Any]:
    return await engine.pause()


@app.post("/sim/speed")
async def sim_speed(body: SpeedBody) -> dict[str, Any]:
    return await engine.set_speed(body.speed_factor)


@app.post("/assets/{asset_id}/availability")
async def asset_availability(asset_id: str, body: AvailabilityBody) -> dict[str, Any]:
    try:
        return await engine.set_availability(asset_id, body.available)
    except KeyError as exc:
        raise HTTPException(404, f"unknown asset {exc}") from exc


@app.post("/assets/{asset_id}/setpoint")
async def asset_setpoint(asset_id: str, body: SetpointBody) -> dict[str, Any]:
    try:
        return await engine.set_setpoint(asset_id, body.setpoint_limit_kw)
    except KeyError as exc:
        raise HTTPException(404, f"unknown asset {exc}") from exc


@app.post("/market/down-regulation")
async def market_down_regulation(body: DownRegBody) -> dict[str, Any]:
    try:
        return await engine.down_regulate(
            body.asset_id, body.setpoint_limit_kw, body.duration_minutes
        )
    except KeyError as exc:
        raise HTTPException(404, f"unknown asset {exc}") from exc


@app.post("/market/bids")
async def market_bids(body: BidBody) -> dict[str, Any]:
    return await engine.place_bid(
        body.portfolio_id,
        body.market_code,
        body.price_eur,
        body.volume_mw,
        body.direction,
        body.accept,
    )


@app.post("/dbt/run")
async def dbt_run(body: DbtBody | None = None) -> dict[str, Any]:
    full_refresh = body.full_refresh if body else False
    return await engine.run_dbt(full_refresh=full_refresh)


@app.get("/reports")
async def reports() -> dict[str, str]:
    return dict(REPORTS)


@app.get("/afrr/recent")
async def afrr_recent() -> dict[str, Any]:
    return {
        "period_seconds": settings.afrr_period_seconds,
        "rows": list(engine.recent_afrr),
    }


@app.post("/iceberg/flush")
async def iceberg_flush() -> dict[str, Any]:
    return await engine.flush_iceberg()


@app.post("/iceberg/maintain")
async def iceberg_maintain() -> dict[str, Any]:
    return await asyncio.to_thread(engine.iceberg.maintain)


@app.get("/iceberg/telemetry")
async def iceberg_telemetry(limit: int = 20) -> list[dict[str, Any]]:
    sql = (
        "SELECT asset_id, event_ts, active_power_kw, ingested_at "
        f"FROM iceberg.{settings.iceberg_namespace}.emsys_telemetry "
        "ORDER BY ingested_at DESC "
        f"LIMIT {int(limit)}"
    )
    try:
        return await trino_query(settings.trino_host, settings.trino_port, sql)
    except Exception as exc:
        raise HTTPException(409, f"Iceberg query failed: {exc}") from exc


@app.get("/reports/{name}")
async def report_rows(name: str, limit: int = 200) -> list[dict[str, Any]]:
    try:
        return await engine.report_rows(name, limit)
    except KeyError as exc:
        raise HTTPException(404, f"unknown report {exc}") from exc
    except Exception as exc:
        raise HTTPException(409, f"report query failed (run dbt first): {exc}") from exc


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    client_id = await hub.connect(websocket)
    await websocket.send_json({"type": "hello", "state": engine.snapshot()})
    await hub.pump(websocket, client_id)
