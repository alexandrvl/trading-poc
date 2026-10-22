from __future__ import annotations

from datetime import datetime, timedelta

from interactive.backend.sim.clock import quarter_hour_start
from interactive.backend.sim.vpp import AssetRuntime, pv_clearsky_kw, wind_power_kw


SIGMA = 0.12


def expected_central_kw(asset: AssetRuntime, target: datetime) -> float:
    tech = asset.technology.upper()
    if tech == "WIND":
        return wind_power_kw(8.5, asset.nominal_kw)
    if tech == "SOLAR":
        return pv_clearsky_kw(target, asset.nominal_kw) * 0.85
    return 0.0


def ensemble_kw(p50: float) -> dict[str, float]:
    return {
        "Ensemble_P50": p50,
        "Ensemble_P90": max(0.0, p50 * (1.0 - 1.282 * SIGMA)),
        "Ensemble_P10": p50 * (1.0 + 1.282 * SIGMA),
        "Intraday_Downscale": p50,
    }


def build_forecast_rows(
    assets: dict[str, AssetRuntime],
    run_ts: datetime,
    start_ts: datetime,
    horizon_hours: int = 6,
) -> list[tuple]:
    start = quarter_hour_start(start_ts)
    rows: list[tuple] = []
    steps = horizon_hours * 4
    for i in range(steps):
        target = start + timedelta(minutes=15 * i)
        for asset in assets.values():
            p50 = expected_central_kw(asset, target)
            values = ensemble_kw(p50)
            wind = asset.wind_speed if asset.technology.upper() == "WIND" else 0.0
            ghi = 640.0 if asset.technology.upper() == "SOLAR" else 0.0
            for type_code, kw in values.items():
                rows.append(
                    (
                        asset.asset_id,
                        run_ts,
                        type_code,
                        target,
                        round(kw, 3),
                        wind,
                        ghi,
                        "METEOLOGICA",
                    )
                )
    return rows
