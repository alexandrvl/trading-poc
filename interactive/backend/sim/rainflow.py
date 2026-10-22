"""ASTM E1049-style rainflow on SoC and a Wöhler-like wear cost. Knobs from sim.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field

from interactive.backend.config import SIM_RAW


def _bess() -> dict:
    return SIM_RAW["bess"]


def turning_points(values: list[float], min_reversal: float = 0.5) -> list[float]:
    if not values:
        return []
    points = [values[0]]
    direction = 0.0
    for x in values[1:]:
        delta = x - points[-1]
        if abs(delta) < min_reversal:
            continue
        sign = 1.0 if delta > 0 else -1.0
        if direction == 0.0 or sign == direction:
            points[-1] = x
            direction = sign
        else:
            points.append(x)
            direction = sign
    if points[-1] != values[-1]:
        points.append(values[-1])
    return points


def rainflow_cycles(peaks: list[float]) -> list[tuple[float, float]]:
    """Return (range, count) with count 1.0 for full cycles and 0.5 for residue."""
    stack: list[float] = []
    closed: list[tuple[float, float]] = []
    for p in peaks:
        stack.append(p)
        while len(stack) >= 3:
            x1, x2, x3 = stack[-3], stack[-2], stack[-1]
            y = abs(x2 - x1)
            x = abs(x3 - x2)
            if x >= y - 1e-12:
                closed.append((y, 1.0))
                stack.pop(-2)
                stack.pop(-2)
            else:
                break
    for i in range(len(stack) - 1):
        closed.append((abs(stack[i + 1] - stack[i]), 0.5))
    return closed


def wohler_cycles_to_failure(dod: float) -> float:
    cfg = _bess()
    dod = max(dod, 0.01)
    return float(cfg["wohler_n_ref"]) * ((float(cfg["wohler_dod_ref"]) / dod) ** float(cfg["wohler_w"]))


def damage_from_range(soc_range_pct: float, count: float) -> float:
    dod = max(soc_range_pct, 0.0) / 100.0
    return count / wohler_cycles_to_failure(dod)


def mfrr_marginal_eur_mwh(
    volume_mw: float,
    duration_h: float | None = None,
    energy_capacity_mwh: float = 1.0,
    replacement_eur: float | None = None,
) -> float:
    if duration_h is None:
        duration_h = SIM_RAW["clock"]["isp_minutes"] / 60.0
    if replacement_eur is None:
        replacement_eur = float(_bess()["replacement_eur"])
    energy_mwh = max(volume_mw * duration_h, 1e-6)
    dod = min(1.0, energy_mwh / max(energy_capacity_mwh, 1e-6))
    cost = damage_from_range(dod * 100.0, 1.0) * replacement_eur
    return cost / energy_mwh


@dataclass
class RainflowSoH:
    replacement_eur: float | None = None
    soh_percent: float = 100.0
    cumulative_cost_eur: float = 0.0
    stack: list[float] = field(default_factory=list)
    last_soc: float | None = None

    def __post_init__(self) -> None:
        if self.replacement_eur is None:
            self.replacement_eur = float(_bess()["replacement_eur"])

    def observe(self, soc_percent: float, min_reversal: float = 0.5) -> float:
        """Stream a SoC sample; charge incremental EUR when a full cycle closes."""
        incremental = 0.0
        if not self.stack:
            self.last_soc = soc_percent
            self.stack = [soc_percent]
            return 0.0
        if abs(soc_percent - self.stack[-1]) < min_reversal:
            self.stack[-1] = soc_percent
            self.last_soc = soc_percent
            return 0.0
        if len(self.stack) == 1:
            self.stack.append(soc_percent)
            self.last_soc = soc_percent
            return 0.0
        last_sign = 1.0 if self.stack[-1] > self.stack[-2] else -1.0
        new_sign = 1.0 if soc_percent > self.stack[-1] else -1.0
        if new_sign == last_sign:
            self.stack[-1] = soc_percent
        else:
            self.stack.append(soc_percent)
        self.last_soc = soc_percent
        while len(self.stack) >= 3:
            x1, x2, x3 = self.stack[-3], self.stack[-2], self.stack[-1]
            y = abs(x2 - x1)
            x = abs(x3 - x2)
            if x >= y - 1e-12:
                dmg = damage_from_range(y, 1.0)
                incremental += dmg * float(self.replacement_eur)
                self.soh_percent = max(0.0, self.soh_percent - dmg * 100.0)
                del self.stack[-3:-1]
            else:
                break
        self.cumulative_cost_eur += incremental
        return incremental


DEFAULT_REPLACEMENT_EUR = float(SIM_RAW["bess"]["replacement_eur"])
