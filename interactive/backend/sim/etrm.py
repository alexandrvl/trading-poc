from __future__ import annotations

import random
from datetime import datetime, timedelta
from uuid import uuid4

from interactive.backend.config import SIM_RAW
from interactive.backend.sim.clock import quarter_hour_start


def _isp_minutes() -> int:
    return int(SIM_RAW["clock"]["isp_minutes"])


def sample_da_price(rng: random.Random, mean: float | None = None, sigma: float | None = None) -> float:
    mean = float(SIM_RAW["markets"]["da_price_mean_eur_mwh"] if mean is None else mean)
    sigma = float(SIM_RAW["markets"]["da_price_sigma_eur_mwh"] if sigma is None else sigma)
    return max(1.0, rng.gauss(mean, sigma))


def da_order_row(
    portfolio_id: str,
    delivery_start: datetime,
    delivery_end: datetime,
    volume_mw: float,
    price_eur: float,
    trade_ts: datetime,
) -> tuple:
    return (
        f"ORD-DA-{portfolio_id}-{delivery_start.strftime('%Y%m%d%H%M')}",
        portfolio_id,
        "NP_DA_EE",
        price_eur,
        volume_mw,
        delivery_start,
        delivery_end,
        "BLOCK",
        "SELL",
        "CONFIRMED",
        trade_ts,
        "PERIOTHEUS",
    )


def settlement_rows(
    portfolio_id: str,
    interval_start: datetime,
    generation_mwh: float,
    forecast_mwh: float,
    da_price: float,
    imb_price: float,
    loaded_at: datetime,
) -> list[tuple]:
    interval_end = interval_start + timedelta(minutes=_isp_minutes())
    delta = generation_mwh - forecast_mwh
    return [
        (
            portfolio_id,
            "NP_DA_EE",
            interval_start,
            interval_end,
            generation_mwh * da_price,
            generation_mwh,
            0.0,
            da_price,
            loaded_at,
            "PERIOTHEUS",
        ),
        (
            portfolio_id,
            "ELERING_IMBALANCE",
            interval_start,
            interval_end,
            0.0,
            delta,
            abs(delta) * imb_price,
            imb_price,
            loaded_at,
            "PERIOTHEUS",
        ),
    ]


def balancing_rows(
    portfolio_id: str,
    interval_start: datetime,
    available: bool,
    afrr_energy_eur: float,
    mfrr_energy_eur: float,
    bbcm_fee: float,
    loaded_at: datetime,
    rng: random.Random | None = None,
) -> list[tuple]:
    interval_end = interval_start + timedelta(minutes=_isp_minutes())
    penalty = 0.0 if available else max(1.0, bbcm_fee * 0.6)
    afrr_cap = bbcm_fee * 1.2
    mfrr_cap = bbcm_fee * 0.3
    fcr_cap = bbcm_fee * 0.4
    rows = [
        (
            portfolio_id,
            "ELERING_aFRR_UP",
            interval_start,
            interval_end,
            afrr_cap,
            afrr_energy_eur,
            0.0,
            loaded_at,
            "PERIOTHEUS",
        ),
        (
            portfolio_id,
            "ELERING_mFRR_UP",
            interval_start,
            interval_end,
            mfrr_cap,
            mfrr_energy_eur,
            0.0,
            loaded_at,
            "PERIOTHEUS",
        ),
        (
            portfolio_id,
            "CAPACITY_MARKET_BALTIC",
            interval_start,
            interval_end,
            bbcm_fee,
            0.0,
            penalty,
            loaded_at,
            "PERIOTHEUS",
        ),
    ]
    if portfolio_id == "Wind_EE_North":
        rows.append(
            (
                portfolio_id,
                "ELERING_FCR",
                interval_start,
                interval_end,
                fcr_cap,
                0.0,
                0.0,
                loaded_at,
                "PERIOTHEUS",
            )
        )
    return rows


def price_rows(
    interval_start: datetime,
    da_price: float,
    mfrr_down_price: float,
    loaded_at: datetime,
) -> list[tuple]:
    interval_end = interval_start + timedelta(minutes=_isp_minutes())
    return [
        ("NP_DA_EE", interval_start, interval_end, da_price, loaded_at, "PERIOTHEUS"),
        (
            "ELERING_mFRR_DOWN",
            interval_start,
            interval_end,
            mfrr_down_price,
            loaded_at,
            "PERIOTHEUS",
        ),
    ]


def down_regulation_event(
    asset_id: str,
    portfolio_id: str,
    start: datetime,
    duration_minutes: int,
    setpoint_kw: float,
) -> tuple:
    interval = quarter_hour_start(start)
    end = start + timedelta(minutes=duration_minutes)
    event_id = f"DR-{asset_id}-{start.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
    return (
        event_id,
        asset_id,
        portfolio_id,
        interval,
        end,
        setpoint_kw,
        "ELERING_DOWN_REGULATION",
        "ELERING_mFRR_DOWN",
        start,
        "PERIOTHEUS",
    )
