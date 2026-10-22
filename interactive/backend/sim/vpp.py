from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime


def wind_power_kw(speed_m_s: float, nominal_kw: float) -> float:
    cut_in, rated, cut_out = 3.0, 12.0, 25.0
    if speed_m_s < cut_in or speed_m_s >= cut_out:
        return 0.0
    if speed_m_s >= rated:
        return nominal_kw
    frac = (speed_m_s - cut_in) / (rated - cut_in)
    return nominal_kw * (frac**3)


def pv_clearsky_kw(ts: datetime, nominal_kw: float) -> float:
    hour = ts.hour + ts.minute / 60.0
    # June Estonia: rough daylight 04:00-22:00, peak near 12:30.
    x = (hour - 4.0) / 18.0
    if x <= 0 or x >= 1:
        return 0.0
    return nominal_kw * (math.sin(math.pi * x) ** 1.2)


@dataclass
class AssetRuntime:
    asset_id: str
    technology: str
    nominal_kw: float
    available: bool = True
    setpoint_limit_kw: float = 0.0
    control_mode: str = "NORMAL"
    soc_percent: float = 55.0
    wind_speed: float = 8.4
    cloud: float = 0.15
    last_unconstrained_kw: float = 0.0
    last_power_kw: float = 0.0
    down_reg_until: datetime | None = None
    energy_kwh: float = 0.0
    rng: random.Random = field(default_factory=random.Random)

    def unconstrained_kw(self, ts: datetime) -> float:
        if not self.available:
            return 0.0
        tech = self.technology.upper()
        if tech == "WIND":
            self.wind_speed = max(
                0.0,
                0.85 * self.wind_speed + 0.15 * 8.5 + self.rng.gauss(0, 0.35),
            )
            return wind_power_kw(self.wind_speed, self.nominal_kw)
        if tech == "SOLAR":
            self.cloud = min(1.0, max(0.0, 0.9 * self.cloud + 0.1 * 0.2 + self.rng.gauss(0, 0.04)))
            return max(0.0, pv_clearsky_kw(ts, self.nominal_kw) * (1.0 - 0.55 * self.cloud))
        if tech == "BESS":
            if self.control_mode == "AFRR":
                return max(-self.nominal_kw, min(self.nominal_kw, self.setpoint_limit_kw))
            return 0.0
        return 0.0

    def step(self, ts: datetime, dt_hours: float = 1.0 / 60.0) -> dict:
        if self.down_reg_until and ts >= self.down_reg_until:
            self.down_reg_until = None
            self.control_mode = "NORMAL"
            self.setpoint_limit_kw = self.nominal_kw

        unconstrained = self.unconstrained_kw(ts)
        self.last_unconstrained_kw = unconstrained
        limit = self.setpoint_limit_kw if self.available else 0.0
        power = min(unconstrained, limit) if unconstrained >= 0 else max(unconstrained, -limit)
        if not self.available:
            power = 0.0

        if self.technology.upper() == "BESS":
            energy_cap = self.nominal_kw * 1.0  # 1-hour duration
            if energy_cap > 0:
                self.soc_percent = min(
                    95.0,
                    max(5.0, self.soc_percent - (power * dt_hours / energy_cap) * 100.0),
                )
            wear = abs(power) * dt_hours * 0.002
        else:
            wear = None

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
            "setpoint_limit_kw": round(limit, 3),
            "control_mode": mode,
            "soc_percent": round(self.soc_percent, 3) if self.technology.upper() == "BESS" else None,
            "degradation_cost_eur": round(wear, 5) if wear is not None else None,
            "availability_status": self.available,
            "unconstrained_kw": round(unconstrained, 3),
            "wind_speed_m_s": round(self.wind_speed, 3) if self.technology.upper() == "WIND" else 0.0,
            "ghi_w_m2": round(800 * (1 - self.cloud), 1) if self.technology.upper() == "SOLAR" else 0.0,
        }


def seed_assets(rows: list[dict], rng_seed: int = 7) -> dict[str, AssetRuntime]:
    assets: dict[str, AssetRuntime] = {}
    for i, row in enumerate(rows):
        rng = random.Random(rng_seed + i)
        assets[row["asset_id"]] = AssetRuntime(
            asset_id=row["asset_id"],
            technology=row["technology"],
            nominal_kw=float(row["nominal_power_kw"]),
            setpoint_limit_kw=float(row["nominal_power_kw"]),
            energy_kwh=float(row["nominal_power_kw"]),
            rng=rng,
            wind_speed=8.0 + rng.random(),
            cloud=0.1 + 0.1 * rng.random(),
        )
    return assets
