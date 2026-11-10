import os

from live_refresh import CHART_CACHE_TIMEOUT

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = os.environ["SUPERSET_METADATA_DB"]
SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

ROW_LIMIT = 5000
SUPERSET_WEBSERVER_TIMEOUT = 120
SQLLAB_TIMEOUT = 120

# Local HTTP. Talisman expects HTTPS and breaks the compose port mapping.
TALISMAN_ENABLED = False
PREVENT_UNSAFE_DB_CONNECTIONS = False
WTF_CSRF_ENABLED = True
WTF_CSRF_TIME_LIMIT = 60 * 60 * 24 * 365


def _redis(index: int) -> str:
    base = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    head, _, tail = base.rpartition("/")
    if tail.isdigit():
        return f"{head}/{index}"
    return f"{base}/{index}"


CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_URL": _redis(0),
    "CACHE_DEFAULT_TIMEOUT": 300,
}
# -1 disables chart-data cache so dbt/sim rows are not held for 10 minutes.
DATA_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_URL": _redis(1),
    "CACHE_DEFAULT_TIMEOUT": CHART_CACHE_TIMEOUT,
}
FILTER_STATE_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_URL": _redis(2),
    "CACHE_DEFAULT_TIMEOUT": 600,
}
EXPLORE_FORM_DATA_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_URL": _redis(3),
    "CACHE_DEFAULT_TIMEOUT": 600,
}
NATIVE_FILTER_OPTIONS_CACHE_TIMEOUT = CHART_CACHE_TIMEOUT
