from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


def _ns(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{k: _ns(v) for k, v in value.items()})
    return value


def _config_path() -> Path:
    env = os.environ.get("SIM_CONFIG")
    if env:
        explicit = Path(env)
        if explicit.is_file():
            return explicit
        raise FileNotFoundError(f"SIM_CONFIG is not a file: {env}")
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "config" / "sim.yaml",
        Path("/app/interactive/config/sim.yaml"),
        Path("interactive/config/sim.yaml"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("sim.yaml not found; set SIM_CONFIG")


def load_sim_dict(path: Path | None = None) -> dict[str, Any]:
    target = path or _config_path()
    with target.open() as handle:
        return yaml.safe_load(handle) or {}


_SIM_RAW = load_sim_dict()
sim = _ns(_SIM_RAW)
SIM_RAW = _SIM_RAW


class Settings(BaseSettings):
    """Process settings. Connection secrets come from the environment, not the repo."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore", case_sensitive=False)

    pghost: str = "localhost"
    pgport: int = 5433
    pguser: str = "dbt_user"
    pgpassword: str = "dbt_password"
    pgdatabase: str = "iceberg_dbt"

    s3_endpoint: str = "localhost:9010"
    s3_access_key: str = "minio_user"
    s3_secret_key: str = "minio_password"
    s3_bucket: str = "iceberg-data"
    s3_region: str = "eu-central-1"
    iceberg_enabled: bool = True
    iceberg_namespace: str = str(_SIM_RAW.get("iceberg", {}).get("namespace", "raw"))
    iceberg_flush_seconds: float = float(_SIM_RAW.get("iceberg", {}).get("flush_seconds", 60))
    iceberg_flush_rows: int = int(_SIM_RAW.get("iceberg", {}).get("flush_rows", 50))
    trino_host: str = "localhost"
    trino_port: int = 8082

    ws_queue_size: int = int(_SIM_RAW.get("clock", {}).get("ws_queue_size", 100))
    ingest_flush_seconds: float = 1.0
    default_speed_factor: float = float(_SIM_RAW.get("clock", {}).get("default_speed_factor", 60))
    sim_start: str = str(_SIM_RAW.get("clock", {}).get("sim_start", "2026-06-02T12:00:00"))
    afrr_period_seconds: float = float(_SIM_RAW.get("clock", {}).get("afrr_period_seconds", 4.0))
    isp_minutes: int = int(_SIM_RAW.get("clock", {}).get("isp_minutes", 15))
    tick_minutes: int = int(_SIM_RAW.get("clock", {}).get("tick_minutes", 1))
    forecast_horizon_hours: int = int(_SIM_RAW.get("forecast", {}).get("horizon_hours", 6))
    da_price_eur_mwh: float = float(_SIM_RAW.get("markets", {}).get("da_price_mean_eur_mwh", 80))
    da_price_sigma_eur_mwh: float = float(_SIM_RAW.get("markets", {}).get("da_price_sigma_eur_mwh", 8))
    imbalance_price_eur_mwh: float = float(_SIM_RAW.get("markets", {}).get("imbalance_price_eur_mwh", 40))
    mfrr_down_price_eur_mwh: float = float(_SIM_RAW.get("markets", {}).get("mfrr_down_price_eur_mwh", 95))
    afrr_price_eur_mwh: float = float(_SIM_RAW.get("markets", {}).get("afrr_price_eur_mwh", 15))
    bbcm_fee_eur: float = float(_SIM_RAW.get("markets", {}).get("bbcm_fee_eur", 10))
    rng_seed: int = int(_SIM_RAW.get("markets", {}).get("rng_seed", 7))

    dbt_project_dir: Path = Path("/opt/trading")
    schema_sql: Path = Path("/opt/init-scripts/03-interactive.sql")

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.pguser}:{self.pgpassword}"
            f"@{self.pghost}:{self.pgport}/{self.pgdatabase}"
        )


settings = Settings()
