"""pvlib PV, Weibull+ARMA wind, cubic power curve. Knobs come from sim.yaml."""

from __future__ import annotations

import math
import random
from datetime import datetime
from functools import lru_cache

import pandas as pd

from interactive.backend.config import SIM_RAW, sim


def _wind() -> object:
    return sim.wind


def _site() -> object:
    return sim.site


def _pv() -> object:
    return sim.pv


def wind_power_kw(
    speed_m_s: float,
    nominal_kw: float,
    cut_in: float | None = None,
    rated: float | None = None,
    cut_out: float | None = None,
) -> float:
    cut_in = _wind().cut_in_ms if cut_in is None else cut_in
    rated = _wind().rated_ms if rated is None else rated
    cut_out = _wind().cut_out_ms if cut_out is None else cut_out
    if speed_m_s < cut_in or speed_m_s >= cut_out:
        return 0.0
    if speed_m_s >= rated:
        return nominal_kw
    frac = (speed_m_s - cut_in) / (rated - cut_in)
    return nominal_kw * (frac**3)


def weibull_sample(rng: random.Random, scale: float | None = None, shape: float | None = None) -> float:
    scale = _wind().weibull_a if scale is None else scale
    shape = _wind().weibull_k if shape is None else shape
    u = min(max(rng.random(), 1e-12), 1 - 1e-12)
    return scale * ((-math.log(u)) ** (1.0 / shape))


class WindARMA:
    """ARMA(1,1) wind speed with Weibull innovations."""

    def __init__(
        self,
        rng: random.Random,
        scale: float | None = None,
        shape: float | None = None,
        start: float | None = None,
    ) -> None:
        self.rng = rng
        self.scale = _wind().weibull_a if scale is None else scale
        self.shape = _wind().weibull_k if shape is None else shape
        self.speed = start if start is not None else self.scale
        self.prev_e = 0.0
        self.phi = _wind().arma_phi
        self.theta = _wind().arma_theta

    def step(self) -> float:
        e = weibull_sample(self.rng, self.scale, self.shape) - self.scale
        nxt = self.phi * self.speed + (1.0 - self.phi) * self.scale + e + self.theta * self.prev_e
        self.prev_e = e
        self.speed = max(0.0, nxt)
        return self.speed


@lru_cache(maxsize=64)
def _location(lat: float, lon: float):
    from pvlib.location import Location

    return Location(lat, lon, tz=_site().timezone, altitude=_site().altitude_m, name=_site().name)


def pvlib_ghi_w_m2(ts: datetime, lat: float | None, lon: float | None) -> float:
    latitude = float(lat if lat is not None else _site().default_lat)
    longitude = float(lon if lon is not None else _site().default_lon)
    loc = _location(round(latitude, 4), round(longitude, 4))
    if ts.tzinfo is None:
        aware = pd.Timestamp(ts).tz_localize(_site().timezone, ambiguous=True, nonexistent="shift_forward")
    else:
        aware = pd.Timestamp(ts).tz_convert(_site().timezone)
    times = pd.DatetimeIndex([aware])
    cs = loc.get_clearsky(times, model=_pv().model)
    return max(0.0, float(cs["ghi"].iloc[0]))


def pv_clearsky_kw(
    ts: datetime,
    nominal_kw: float,
    lat: float | None = None,
    lon: float | None = None,
) -> float:
    ghi = pvlib_ghi_w_m2(ts, lat, lon)
    return max(0.0, min(nominal_kw, nominal_kw * (ghi / _pv().stc_ghi_w_m2)))


# Re-exports used by tests and overlays
EE_DEFAULT_LAT = float(SIM_RAW["site"]["default_lat"])
EE_DEFAULT_LON = float(SIM_RAW["site"]["default_lon"])
WEIBULL_A_MS = float(SIM_RAW["wind"]["weibull_a"])
WEIBULL_K = float(SIM_RAW["wind"]["weibull_k"])
CUT_IN_MS = float(SIM_RAW["wind"]["cut_in_ms"])
RATED_MS = float(SIM_RAW["wind"]["rated_ms"])
CUT_OUT_MS = float(SIM_RAW["wind"]["cut_out_ms"])
