from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from interactive.backend.config import SIM_RAW


def quarter_hour_start(ts: datetime, isp_minutes: int | None = None) -> datetime:
    isp = int(SIM_RAW["clock"]["isp_minutes"] if isp_minutes is None else isp_minutes)
    return ts.replace(minute=(ts.minute // isp) * isp, second=0, microsecond=0)


@dataclass
class SimClock:
    sim_ts: datetime
    running: bool = False
    speed_factor: float = 60.0

    def step_minutes(self, minutes: int | None = None) -> datetime:
        if minutes is None:
            minutes = int(SIM_RAW["clock"]["tick_minutes"])
        self.sim_ts = self.sim_ts + timedelta(minutes=minutes)
        return self.sim_ts

    def wall_sleep_seconds(self, sim_minutes: float | None = None) -> float:
        if sim_minutes is None:
            sim_minutes = float(SIM_RAW["clock"]["tick_minutes"])
        speed = max(self.speed_factor, 0.1)
        return max(0.05, (sim_minutes * 60.0) / speed)
