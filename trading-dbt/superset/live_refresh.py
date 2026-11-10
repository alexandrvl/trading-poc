"""How the billing dashboard stays current with sim / dbt / Iceberg marts.

Apache Superset 5: chart-data ``cache_timeout`` of ``-1`` disables the data
cache (live query). ``0`` is backend-specific and must not be used to mean
“no cache”. Dashboard ``refresh_frequency`` is the browser poll in seconds.
There is no REST rebuild for dbt or Iceberg flush.
"""

from __future__ import annotations

import os

CHART_CACHE_TIMEOUT = int(os.environ.get("SUPERSET_CHART_CACHE_TIMEOUT", "-1"))
DASHBOARD_REFRESH_SECONDS = int(os.environ.get("SUPERSET_DASHBOARD_REFRESH_SECONDS", "60"))
WAREHOUSE_URI = os.environ.get("SUPERSET_WAREHOUSE_URI", "trino://trino@trino:8080/iceberg")
WAREHOUSE_NAME = os.environ.get("SUPERSET_WAREHOUSE_NAME", "Iceberg")
MART_SCHEMA = os.environ.get("SUPERSET_MART_SCHEMA", "information_mart")


def rows_after_change(
    previous: list,
    current: list,
    *,
    elapsed_seconds: float,
    cache_timeout: int = CHART_CACHE_TIMEOUT,
    refresh_seconds: int = DASHBOARD_REFRESH_SECONDS,
) -> list:
    """Rows a dashboard would show after the mart changed, without force-refresh.

    The browser only re-queries when ``refresh_seconds`` has elapsed. Cached
    chart data is reused until ``cache_timeout`` (ignored when ``-1``).
    """
    if refresh_seconds <= 0:
        return list(previous)
    if elapsed_seconds < refresh_seconds:
        return list(previous)
    if cache_timeout == -1:
        return list(current)
    if cache_timeout > 0 and elapsed_seconds < cache_timeout:
        return list(previous)
    return list(current)
