from datetime import datetime

import pytest

from interactive.backend.sim.engine import SimEngine
from interactive.backend.sim.rainflow import RainflowSoH, mfrr_marginal_eur_mwh
from interactive.backend.sim.vpp import AssetRuntime
from interactive.backend.ws import ConnectionManager


def test_charge_discharge_cycle_increases_degradation_cost() -> None:
    rf = RainflowSoH()
    for soc in (20.0, 80.0, 20.0, 80.0, 25.0):
        rf.observe(soc, min_reversal=0.1)
    assert rf.cumulative_cost_eur > 0
    assert rf.soh_percent < 100


def test_bess_step_records_soh() -> None:
    asset = AssetRuntime(
        asset_id="BESS-EE-01",
        technology="BESS",
        nominal_kw=1000,
        setpoint_limit_kw=800,
        control_mode="AFRR",
        soc_percent=50.0,
    )
    sample = asset.step(datetime(2026, 6, 2, 12, 0), dt_hours=0.25)
    assert sample["soh_percent"] is not None
    assert sample["soc_percent"] < 50.0


def test_cheap_mfrr_is_below_wear_floor() -> None:
    floor = mfrr_marginal_eur_mwh(1.0, duration_h=0.25, energy_capacity_mwh=1.0)
    assert floor > 10.0


@pytest.mark.asyncio
async def test_place_bid_rejects_cheap_mfrr(monkeypatch) -> None:
    engine = SimEngine(ConnectionManager())
    bess = AssetRuntime(
        asset_id="BESS-EE-01",
        technology="BESS",
        nominal_kw=1000,
        setpoint_limit_kw=1000,
        soc_percent=55.0,
    )
    engine.assets = {"BESS-EE-01": bess}
    engine.membership = {"BESS-EE-01": "Wind_EE_North"}

    async def fake_execute(*_args, **_kwargs):
        return None

    monkeypatch.setattr("interactive.backend.sim.engine.db.execute", fake_execute)
    cheap = await engine.place_bid("Wind_EE_North", "ELERING_mFRR_UP", 5.0, 1.0)
    assert cheap["order_status"] == "REJECTED"
    assert cheap["wear_floor_eur_mwh"] > 5.0
    rich = await engine.place_bid("Wind_EE_North", "ELERING_mFRR_UP", 10_000.0, 1.0)
    assert rich["order_status"] in {"CONFIRMED", "REPRICED"}
