from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime

from interactive.backend.config import SIM_RAW
from interactive.backend.sim.physics import (
    CUT_IN_MS,
    CUT_OUT_MS,
    EE_DEFAULT_LAT,
    EE_DEFAULT_LON,
    RATED_MS,
    WEIBULL_A_MS,
    WEIBULL_K,
    WindARMA,
    pv_clearsky_kw,
    pvlib_ghi_w_m2,
    wind_power_kw,
)
from interactive.backend.sim.rainflow import (
    DEFAULT_REPLACEMENT_EUR,
    RainflowSoH,
    mfrr_marginal_eur_mwh,
)


def _asset_overlay(asset_id: str) -> dict:
    return dict(SIM_RAW.get("assets") or {}).get(asset_id) or {}


@dataclass
class AssetRuntime:
    asset_id: str
    technology: str
    nominal_kw: float
    latitude: float = EE_DEFAULT_LAT
    longitude: float = EE_DEFAULT_LON
    available: bool = True
    setpoint_limit_kw: float = 0.0
    control_mode: str = "NORMAL"
    soc_percent: float = field(default_factory=lambda: float(SIM_RAW["bess"]["initial_soc_percent"]))
    wind_speed: float = WEIBULL_A_MS
    cloud: float = field(default_factory=lambda: float(SIM_RAW["pv"]["cloud_mean"]))
    last_unconstrained_kw: float = 0.0
    last_power_kw: float = 0.0
    last_ghi: float = 0.0
    down_reg_until: datetime | None = None
    energy_kwh: float = 0.0
    weibull_a: float = WEIBULL_A_MS
    weibull_k: float = WEIBULL_K
    cut_in: float = CUT_IN_MS
    rated: float = RATED_MS
    cut_out: float = CUT_OUT_MS
    replacement_eur: float = DEFAULT_REPLACEMENT_EUR
    rng: random.Random = field(default_factory=random.Random)
    wind_model: WindARMA | None = None
    rainflow: RainflowSoH | None = None

    def __post_init__(self) -> None:
        if self.technology.upper() == "WIND" and self.wind_model is None:
            self.wind_model = WindARMA(
                self.rng, scale=self.weibull_a, shape=self.weibull_k, start=self.wind_speed
            )
        if self.technology.upper() == "BESS" and self.rainflow is None:
            self.rainflow = RainflowSoH(replacement_eur=self.replacement_eur)
            self.rainflow.observe(self.soc_percent)

    def unconstrained_kw(self, ts: datetime) -> float:
        if not self.available:
            return 0.0
        tech = self.technology.upper()
        pv_cfg = SIM_RAW["pv"]
        if tech == "WIND":
            assert self.wind_model is not None
            self.wind_speed = self.wind_model.step()
            return wind_power_kw(
                self.wind_speed,
                self.nominal_kw,
                cut_in=self.cut_in,
                rated=self.rated,
                cut_out=self.cut_out,
            )
        if tech == "SOLAR":
            self.cloud = min(
                1.0,
                max(
                    0.0,
                    float(pv_cfg["cloud_ar"]) * self.cloud
                    + (1.0 - float(pv_cfg["cloud_ar"])) * float(pv_cfg["cloud_mean"])
                    + self.rng.gauss(0, float(pv_cfg["cloud_noise"])),
                ),
            )
            clear = pv_clearsky_kw(ts, self.nominal_kw, self.latitude, self.longitude)
            ghi = pvlib_ghi_w_m2(ts, self.latitude, self.longitude)
            self.last_ghi = ghi * (1.0 - float(pv_cfg["cloud_attenuation"]) * self.cloud)
            return max(0.0, min(self.nominal_kw, clear * (1.0 - float(pv_cfg["cloud_attenuation"]) * self.cloud)))
        if tech == "BESS":
            if self.control_mode in ("AFRR", "EXTERNAL_CONTROL"):
                return max(-self.nominal_kw, min(self.nominal_kw, self.setpoint_limit_kw))
            return 0.0
        return 0.0

    def step(self, ts: datetime, dt_hours: float | None = None) -> dict:
        if dt_hours is None:
            dt_hours = float(SIM_RAW["clock"]["tick_minutes"]) / 60.0
        if self.down_reg_until and ts >= self.down_reg_until:
            self.down_reg_until = None
            self.control_mode = "NORMAL"
            self.setpoint_limit_kw = self.nominal_kw

        unconstrained = self.unconstrained_kw(ts)
        self.last_unconstrained_kw = unconstrained
        bess_cfg = SIM_RAW["bess"]
        if self.technology.upper() == "BESS":
            power = unconstrained if self.available else 0.0
        else:
            limit = self.setpoint_limit_kw if self.available else 0.0
            power = min(unconstrained, limit) if unconstrained >= 0 else max(unconstrained, -abs(limit))
        if not self.available:
            power = 0.0

        wear = None
        soh = None
        if self.technology.upper() == "BESS":
            energy_cap = self.energy_kwh or (self.nominal_kw * float(bess_cfg["duration_hours"]))
            if energy_cap > 0:
                self.soc_percent = min(
                    float(bess_cfg["soc_max_percent"]),
                    max(
                        float(bess_cfg["soc_min_percent"]),
                        self.soc_percent - (power * dt_hours / energy_cap) * 100.0,
                    ),
                )
            assert self.rainflow is not None
            wear = self.rainflow.observe(self.soc_percent)
            soh = self.rainflow.soh_percent

        self.last_power_kw = power
        if not self.available:
            status, mode = "UNAVAILABLE", "NORMAL"
        elif self.control_mode == "EXTERNAL_CONTROL":
            status, mode = "EXTERNAL_CONTROL", "EXTERNAL_CONTROL"
        elif self.control_mode == "AFRR":
            status, mode = "PRODUCING", "AFRR"
        elif self.technology.upper() == "BESS" and abs(power) < 1:
            status, mode = "STANDBY", "NORMAL"
        elif unconstrained > 1 and power < 0.9 * unconstrained:
            status, mode = "DERATED", self.control_mode
        else:
            status, mode = "PRODUCING", self.control_mode

        return {
            "asset_id": self.asset_id,
            "event_ts": ts,
            "active_power_kw": round(power, 3),
            "reactive_power_kvar": round(abs(power) * 0.04, 3),
            "turbine_status": status,
            "setpoint_limit_kw": round(self.setpoint_limit_kw if self.available else 0.0, 3),
            "control_mode": mode,
            "soc_percent": round(self.soc_percent, 3) if self.technology.upper() == "BESS" else None,
            "degradation_cost_eur": round(wear, 5) if wear is not None else None,
            "soh_percent": round(soh, 4) if soh is not None else None,
            "availability_status": self.available,
            "unconstrained_kw": round(unconstrained, 3),
            "wind_speed_m_s": round(self.wind_speed, 3) if self.technology.upper() == "WIND" else 0.0,
            "ghi_w_m2": round(self.last_ghi, 1) if self.technology.upper() == "SOLAR" else 0.0,
        }

    def mfrr_floor_eur_mwh(self, volume_mw: float, duration_h: float | None = None) -> float:
        energy_mwh = (self.energy_kwh or self.nominal_kw) / 1000.0
        return mfrr_marginal_eur_mwh(
            volume_mw,
            duration_h=duration_h,
            energy_capacity_mwh=energy_mwh,
            replacement_eur=self.replacement_eur,
        )


def seed_assets(rows: list[dict], rng_seed: int | None = None) -> dict[str, AssetRuntime]:
    if rng_seed is None:
        rng_seed = int(SIM_RAW["markets"]["rng_seed"])
    assets: dict[str, AssetRuntime] = {}
    for i, row in enumerate(rows):
        rng = random.Random(rng_seed + i)
        overlay = _asset_overlay(row["asset_id"])
        lat = row.get("latitude")
        lon = row.get("longitude")
        assets[row["asset_id"]] = AssetRuntime(
            asset_id=row["asset_id"],
            technology=row["technology"],
            nominal_kw=float(row["nominal_power_kw"]),
            latitude=float(lat) if lat is not None else EE_DEFAULT_LAT,
            longitude=float(lon) if lon is not None else EE_DEFAULT_LON,
            setpoint_limit_kw=float(row["nominal_power_kw"]),
            energy_kwh=float(row["nominal_power_kw"]) * float(SIM_RAW["bess"]["duration_hours"]),
            rng=rng,
            wind_speed=WEIBULL_A_MS * (0.9 + 0.2 * rng.random()),
            cloud=float(overlay.get("cloud_mean", SIM_RAW["pv"]["cloud_mean"])),
            weibull_a=float(overlay.get("weibull_a", WEIBULL_A_MS)),
            weibull_k=float(overlay.get("weibull_k", WEIBULL_K)),
            replacement_eur=float(overlay.get("replacement_eur", DEFAULT_REPLACEMENT_EUR)),
        )
    return assets
