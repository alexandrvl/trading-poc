from __future__ import annotations

from datetime import datetime, timedelta

from interactive.backend.config import SIM_RAW
from interactive.backend.sim.clock import quarter_hour_start
from interactive.backend.sim.vpp import AssetRuntime, pv_clearsky_kw, wind_power_kw


def expected_central_kw(asset: AssetRuntime, target: datetime) -> float:
    tech = asset.technology.upper()
    if tech == "WIND":
        return wind_power_kw(asset.weibull_a, asset.nominal_kw, asset.cut_in, asset.rated, asset.cut_out)
    if tech == "SOLAR":
        return pv_clearsky_kw(target, asset.nominal_kw, asset.latitude, asset.longitude) * (
            1.0 - float(SIM_RAW["pv"]["cloud_attenuation"]) * asset.cloud
        )
    return 0.0


def ensemble_kw(p50: float, sigma: float | None = None) -> dict[str, float]:
    sigma = float(SIM_RAW["forecast"]["sigma"] if sigma is None else sigma)
    return {
        "Ensemble_P50": p50,
        "Ensemble_P90": max(0.0, p50 * (1.0 - 1.282 * sigma)),
        "Ensemble_P10": p50 * (1.0 + 1.282 * sigma),
        "Intraday_Downscale": p50,
    }


def build_forecast_rows(
    assets: dict[str, AssetRuntime],
    run_ts: datetime,
    start_ts: datetime,
    horizon_hours: int | None = None,
) -> list[tuple]:
    if horizon_hours is None:
        horizon_hours = int(SIM_RAW["forecast"]["horizon_hours"])
    isp = int(SIM_RAW["clock"]["isp_minutes"])
    start = quarter_hour_start(start_ts)
    rows: list[tuple] = []
    steps = int(horizon_hours * 60 / isp)
    for i in range(steps):
        target = start + timedelta(minutes=isp * i)
        for asset in assets.values():
            p50 = expected_central_kw(asset, target)
            values = ensemble_kw(p50)
            wind = asset.wind_speed if asset.technology.upper() == "WIND" else 0.0
            ghi = asset.last_ghi if asset.technology.upper() == "SOLAR" else 0.0
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
