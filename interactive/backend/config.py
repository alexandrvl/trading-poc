from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore", case_sensitive=False)

    pghost: str = "localhost"
    pgport: int = 5433
    pguser: str = "dbt_user"
    pgpassword: str = "dbt_password"
    pgdatabase: str = "iceberg_dbt"

    ws_queue_size: int = 100
    ingest_flush_seconds: float = 1.0
    default_speed_factor: float = 60.0
    sim_start: str = "2026-06-02T12:00:00"
    afrr_period_seconds: float = 1.0
    forecast_horizon_hours: int = 6
    da_price_eur_mwh: float = 80.0
    imbalance_price_eur_mwh: float = 40.0
    mfrr_down_price_eur_mwh: float = 95.0
    bbcm_fee_eur: float = 10.0

    dbt_project_dir: Path = Path("/opt/trading")
    schema_sql: Path = Path("/opt/init-scripts/03-interactive.sql")

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.pguser}:{self.pgpassword}"
            f"@{self.pghost}:{self.pgport}/{self.pgdatabase}"
        )


settings = Settings()
