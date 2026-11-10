from pathlib import Path

import asyncio

import pytest
from fastapi.routing import APIRoute

from interactive.backend.config import SIM_RAW, settings
from interactive.backend.iceberg_ingest import IcebergSink
from interactive.backend.main import app
from interactive.backend.sim.engine import SimEngine
from interactive.backend.ws import ConnectionManager


def _api_paths() -> set[str]:
    return {route.path for route in app.routes if isinstance(route, APIRoute)}


def test_dbt_and_iceberg_intervals_come_from_yaml() -> None:
    assert SIM_RAW["dbt"]["run_every_minutes"] == 1
    assert settings.dbt_run_every_minutes == 1
    assert SIM_RAW["iceberg"]["flush_seconds"] == 60
    assert SIM_RAW["iceberg"]["flush_rows"] == 50
    assert settings.iceberg_flush_seconds == 60
    assert settings.iceberg_flush_rows == 50


def test_dbt_run_and_iceberg_flush_routes_are_absent() -> None:
    paths = _api_paths()
    assert "/dbt/run" not in paths
    assert "/iceberg/flush" not in paths
    assert "/reports/{name}" in paths
    assert "/iceberg/telemetry" in paths
    assert "/telemetry/history" in paths


def test_ui_does_not_post_dbt_or_iceberg_flush() -> None:
    ui = (Path(__file__).resolve().parents[1] / "ui" / "streamlit_app.py").read_text()
    assert "/dbt/run" not in ui
    assert "/iceberg/flush" not in ui
    assert "Flush Iceberg now" not in ui
    assert "Refresh reports (dbt run)" not in ui


def test_iceberg_flushes_when_age_exceeds_yaml_seconds() -> None:
    from types import SimpleNamespace

    sink = IcebergSink(
        SimpleNamespace(
            iceberg_enabled=True,
            iceberg_flush_rows=10_000,
            iceberg_flush_seconds=0.0,
        )
    )
    sink.enqueue_telemetry([{"asset_id": "WT-EE-N-01"}])
    assert sink.should_flush()


@pytest.mark.asyncio
async def test_dbt_loop_waits_configured_minutes_then_runs(monkeypatch) -> None:
    engine = SimEngine(ConnectionManager())
    slept: list[float] = []
    runs: list[dict] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        if len(slept) >= 2:
            raise asyncio.CancelledError()

    async def fake_run_dbt(full_refresh: bool = False) -> dict:
        runs.append({"full_refresh": full_refresh})
        return {"status": "ok"}

    monkeypatch.setattr("interactive.backend.sim.engine.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(engine, "run_dbt", fake_run_dbt)
    with pytest.raises(asyncio.CancelledError):
        await engine._dbt_loop()
    assert slept[0] == pytest.approx(settings.dbt_run_every_minutes * 60.0)
    assert runs == [{"full_refresh": False}]


@pytest.mark.asyncio
async def test_iceberg_loop_flushes_when_scheduler_says_so(monkeypatch) -> None:
    engine = SimEngine(ConnectionManager())
    slept: list[float] = []
    flushed: list[str] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        if len(slept) >= 2:
            raise asyncio.CancelledError()

    async def fake_to_thread(fn, *args):
        return fn(*args)

    monkeypatch.setattr("interactive.backend.sim.engine.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("interactive.backend.sim.engine.asyncio.to_thread", fake_to_thread)
    engine.iceberg.should_flush = lambda: True  # type: ignore[method-assign]
    engine.iceberg.flush = lambda: flushed.append("flush") or {"status": "ok", "rows": 1}  # type: ignore[method-assign]
    with pytest.raises(asyncio.CancelledError):
        await engine._iceberg_loop()
    assert slept[0] <= settings.iceberg_flush_seconds
    assert flushed == ["flush"]


@pytest.mark.asyncio
async def test_ensure_jobs_starts_dbt_and_iceberg_tasks() -> None:
    engine = SimEngine(ConnectionManager())
    engine.ensure_jobs()
    assert engine._dbt_task is not None and engine._dbt_task.get_name() == "dbt"
    assert engine._iceberg_task is not None and engine._iceberg_task.get_name() == "iceberg"
    engine._dbt_task.cancel()
    engine._iceberg_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await engine._dbt_task
    with pytest.raises(asyncio.CancelledError):
        await engine._iceberg_task
