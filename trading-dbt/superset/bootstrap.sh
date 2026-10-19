#!/usr/bin/env bash
# Create the metadata database, load permissions, publish the billing dashboard, then serve.
set -euo pipefail

python <<'PY'
import os
import time

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine.url import make_url

url = make_url(os.environ["SUPERSET_METADATA_DB"])
last_error = None
for _ in range(30):
    try:
        conn = psycopg2.connect(
            host=url.host,
            port=url.port or 5432,
            user=url.username,
            password=url.password,
            dbname="postgres",
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (url.database,))
        if cur.fetchone() is None:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(url.database)))
            print(f"created metadata database {url.database}", flush=True)
        else:
            print(f"metadata database {url.database} already exists", flush=True)
        cur.close()
        conn.close()
        break
    except Exception as exc:  # noqa: BLE001 - postgres may still be starting
        last_error = exc
        print(f"waiting for postgres: {exc}", flush=True)
        time.sleep(2)
else:
    raise SystemExit(f"could not create the superset database: {last_error}")
PY

superset db upgrade
superset fab create-admin \
    --username admin \
    --firstname Admin \
    --lastname User \
    --email admin@localhost \
    --password admin \
    || echo "admin user already exists"
superset init
python /app/docker/bootstrap_bi.py

exec gunicorn \
    --bind "0.0.0.0:${SUPERSET_PORT:-8088}" \
    --workers "${SERVER_WORKER_AMOUNT:-1}" \
    --worker-class "${SERVER_WORKER_CLASS:-gthread}" \
    --threads "${SERVER_THREADS_AMOUNT:-8}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    "${FLASK_APP:-superset.app:create_app()}"
