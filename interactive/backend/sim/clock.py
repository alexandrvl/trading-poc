from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


def quarter_hour_start(ts: datetime) -> datetime:
    return ts.replace(minute=(ts.minute // 15) * 15, second=0, microsecond=0)


@dataclass
class SimClock:
    sim_ts: datetime
    running: bool = False
    speed_factor: float = 60.0

    def step_minutes(self, minutes: int = 1) -> datetime:
        self.sim_ts = self.sim_ts + timedelta(minutes=minutes)
        return self.sim_ts

    def wall_sleep_seconds(self, sim_minutes: float = 1.0) -> float:
        speed = max(self.speed_factor, 0.1)
        return max(0.05, (sim_minutes * 60.0) / speed)
