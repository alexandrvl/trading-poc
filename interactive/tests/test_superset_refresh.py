from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

from interactive.backend.config import SIM_RAW
from interactive.backend.main import app
from fastapi.routing import APIRoute

ROOT = Path(__file__).resolve().parents[2]
SUPERSET = ROOT / "trading-dbt" / "superset"


def _load_live_refresh():
    spec = importlib.util.spec_from_file_location("live_refresh", SUPERSET / "live_refresh.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _api_paths() -> set[str]:
    return {route.path for route in app.routes if isinstance(route, APIRoute)}


def test_chart_data_cache_is_disabled_for_live_queries() -> None:
    live = _load_live_refresh()
    config = (SUPERSET / "superset_config.py").read_text()
    bootstrap = (SUPERSET / "bootstrap_bi.py").read_text()
    assert live.CHART_CACHE_TIMEOUT == -1
    data_cache = config[config.index("DATA_CACHE_CONFIG") : config.index("FILTER_STATE_CACHE_CONFIG")]
    assert "CHART_CACHE_TIMEOUT" in data_cache
    assert "600" not in data_cache
    assert "DATA_CACHE_CONFIG" in config
    assert "chart.cache_timeout = CHART_CACHE_TIMEOUT" in bootstrap
    assert "dataset.cache_timeout = CHART_CACHE_TIMEOUT" in bootstrap
    assert "database.cache_timeout = CHART_CACHE_TIMEOUT" in bootstrap


def test_dashboard_refresh_is_scheduled_not_clicked() -> None:
    live = _load_live_refresh()
    bootstrap = (SUPERSET / "bootstrap_bi.py").read_text()
    dbt_seconds = int(SIM_RAW["dbt"]["run_every_minutes"]) * 60
    assert live.DASHBOARD_REFRESH_SECONDS > 0
    assert live.DASHBOARD_REFRESH_SECONDS <= dbt_seconds
    assert '"refresh_frequency": 0' not in bootstrap
    assert '"refresh_frequency": DASHBOARD_REFRESH_SECONDS' in bootstrap
    assert "timed_refresh_immune_slices" in bootstrap


def test_new_mart_row_appears_without_force_refresh() -> None:
    live = _load_live_refresh()
    previous = [{"asset_id": "WT-EE-N-01", "lost_energy_mwh": 0.0, "compensation_eur": 0.0}]
    current = [{"asset_id": "WT-EE-N-01", "lost_energy_mwh": 0.4, "compensation_eur": 38.0}]
    shown = live.rows_after_change(
        previous,
        current,
        elapsed_seconds=live.DASHBOARD_REFRESH_SECONDS,
    )
    assert shown == current
    still_cached = live.rows_after_change(previous, current, elapsed_seconds=0)
    assert still_cached == previous


def test_ten_minute_cache_and_no_poll_would_stay_stale() -> None:
    live = _load_live_refresh()
    previous = [{"compensation_eur": 0.0}]
    current = [{"compensation_eur": 38.0}]
    stale = live.rows_after_change(
        previous,
        current,
        elapsed_seconds=60,
        cache_timeout=600,
        refresh_seconds=0,
    )
    assert stale == previous
    assert live.CHART_CACHE_TIMEOUT != 600
    assert live.DASHBOARD_REFRESH_SECONDS != 0


def test_dashboard_reads_live_marts_not_a_rebuild_endpoint() -> None:
    bootstrap = (SUPERSET / "bootstrap_bi.py").read_text()
    tree = ast.parse(bootstrap)
    datasets = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "DATASETS":
                    datasets = ast.literal_eval(node.value)
    assert datasets is not None
    assert "mart_curtailment_compensation" in datasets
    assert "mart_asset_internal_billing" in datasets
    assert "mart_portfolio_reconciliation" in datasets
    paths = _api_paths()
    assert "/dbt/run" not in paths
    assert "/iceberg/flush" not in paths
    assert "/dbt/run" not in bootstrap
    assert "/iceberg/flush" not in bootstrap
    compose = (ROOT / "docker-compose.interactive.yml").read_text()
    assert "trading-poc-superset" in compose
    assert "SUPERSET_WAREHOUSE_URI: postgresql+psycopg2://" in compose
