from datetime import datetime

from interactive.backend.sim.forecasts import ensemble_kw
from interactive.backend.sim.vpp import AssetRuntime, pv_clearsky_kw, wind_power_kw


def test_wind_curve_clips_and_rates() -> None:
    assert wind_power_kw(2.0, 3000) == 0
    assert wind_power_kw(12.0, 3000) == 3000
    assert wind_power_kw(25.0, 3000) == 0
    mid = wind_power_kw(7.5, 3000)
    assert 0 < mid < 3000


def test_pv_is_zero_at_night() -> None:
    night = datetime(2026, 6, 2, 1, 0)
    noon = datetime(2026, 6, 2, 12, 30)
    assert pv_clearsky_kw(night, 1500) == 0
    assert pv_clearsky_kw(noon, 1500) > 1000


def test_setpoint_is_honored() -> None:
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


def test_unavailable_is_zero() -> None:
    asset = AssetRuntime(
        asset_id="WT-EE-N-02",
        technology="WIND",
        nominal_kw=3000,
        available=False,
        setpoint_limit_kw=3000,
        wind_speed=14.0,
    )
    sample = asset.step(datetime(2026, 6, 2, 12, 0))
    assert sample["active_power_kw"] == 0
    assert sample["availability_status"] is False


def test_bess_soc_moves() -> None:
    asset = AssetRuntime(
        asset_id="BESS-EE-01",
        technology="BESS",
        nominal_kw=1000,
        setpoint_limit_kw=500,
        control_mode="AFRR",
        soc_percent=50.0,
    )
    before = asset.soc_percent
    asset.step(datetime(2026, 6, 2, 12, 0), dt_hours=0.25)
    assert asset.soc_percent < before


def test_ensemble_p90_is_conservative() -> None:
    values = ensemble_kw(2000.0)
    assert values["Ensemble_P90"] < values["Ensemble_P50"] < values["Ensemble_P10"]
    assert values["Intraday_Downscale"] == values["Ensemble_P50"]
