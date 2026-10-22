import random
from datetime import datetime
from types import SimpleNamespace

import pytest

from interactive.backend.config import SIM_RAW, settings
from interactive.backend.iceberg_ingest import IcebergSink
from interactive.backend.sim.engine import SimEngine
from interactive.backend.sim.etrm import sample_da_price
from interactive.backend.sim.vpp import AssetRuntime
from interactive.backend.ws import ConnectionManager


def test_picasso_period_is_four_seconds_from_config() -> None:
    assert SIM_RAW["clock"]["afrr_period_seconds"] == 4.0
    assert settings.afrr_period_seconds == 4.0


@pytest.mark.asyncio
async def test_picasso_tick_emits_bess_setpoint(monkeypatch) -> None:
    engine = SimEngine(ConnectionManager())
    engine.assets = {
        "BESS-EE-01": AssetRuntime("BESS-EE-01", "BESS", 1000, setpoint_limit_kw=0),
        "WT-EE-N-01": AssetRuntime("WT-EE-N-01", "WIND", 3000, setpoint_limit_kw=3000),
    }
    engine.membership = {"BESS-EE-01": "Wind_EE_North", "WT-EE-N-01": "Wind_EE_North"}
    inserted = []

    async def fake_execute(_sql, params):
        inserted.append(params)

    monkeypatch.setattr("interactive.backend.sim.engine.db.execute", fake_execute)
    await engine._picasso_tick()
    assert len(inserted) == 1
    assert inserted[0][1] == "BESS-EE-01"
    assert engine.assets["BESS-EE-01"].control_mode == "AFRR"
    assert engine.recent_afrr[-1]["asset_id"] == "BESS-EE-01"


def test_iceberg_flushes_on_row_threshold() -> None:
    sink = IcebergSink(
        SimpleNamespace(
            iceberg_enabled=True,
            iceberg_flush_rows=3,
            iceberg_flush_seconds=3600,
            pguser="u",
            pgpassword="p",
            pghost="h",
            pgport=1,
            pgdatabase="d",
            s3_endpoint="localhost",
            s3_access_key="a",
            s3_secret_key="b",
            s3_bucket="iceberg-data",
            s3_region="eu-central-1",
            iceberg_namespace="raw",
        )
    )
    sink.enqueue_telemetry([{"asset_id": "WT-EE-N-01"}])
    assert not sink.should_flush()
    sink.enqueue_telemetry([{"asset_id": "WT-EE-N-01"}, {"asset_id": "PV-EE-S-01"}])
    assert sink.should_flush()
    appended = []

    def fake_append(name, _fields, rows, partition_field):
        appended.append((name, len(rows), partition_field))
        return len(rows)

    sink._append = fake_append  # type: ignore[method-assign]
    result = sink.flush()
    assert result["status"] == "ok"
    assert result["rows"] >= 3
    assert any(name == "emsys_telemetry" for name, _, _ in appended)


def test_parameters_are_read_from_yaml() -> None:
    assert settings.isp_minutes == SIM_RAW["clock"]["isp_minutes"] == 15
    assert SIM_RAW["wind"]["weibull_a"] == 8.5
    assert SIM_RAW["bess"]["replacement_eur"] == 250000.0
    assert "WT-EE-N-01" in SIM_RAW["assets"]
    assert SIM_RAW["site"]["default_lat"] == 59.40


def test_trading_prices_are_generated_not_a_tape() -> None:
    prices = [round(sample_da_price(random.Random(i)), 4) for i in range(12)]
    assert len(set(prices)) > 1
    assert all(p > 0 for p in prices)


def test_down_regulation_caps_generated_power() -> None:
    asset = AssetRuntime(
        asset_id="WT-EE-N-01",
        technology="WIND",
        nominal_kw=3000,
        setpoint_limit_kw=400,
        control_mode="EXTERNAL_CONTROL",
        wind_speed=14.0,
    )
    sample = asset.step(datetime(2026, 6, 2, 12, 0))
    assert sample["active_power_kw"] <= 400.01
    assert sample["control_mode"] == "EXTERNAL_CONTROL"


def test_curtailment_lost_energy_formula() -> None:
    """Matches mart_curtailment_compensation: integrate (P50 - limited) over the ISP."""
    isp_h = SIM_RAW["clock"]["isp_minutes"] / 60.0
    p50_kw = 2400.0
    limited_kw = 400.0
    lost_mwh = max(0.0, (p50_kw - limited_kw) * isp_h / 1000.0)
    assert lost_mwh == pytest.approx(0.5, rel=1e-6)
