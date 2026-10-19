FROM apache/superset:5.0.0

USER root

# The lean image does not ship a Trino SQLAlchemy driver or the Postgres extra.
RUN uv pip install --python /app/.venv/bin/python \
        "trino==0.330.0" \
        "psycopg2-binary==2.9.10"

COPY superset_config.py /app/pythonpath/superset_config.py
COPY bootstrap.sh /app/docker/bootstrap.sh
COPY bootstrap_bi.py /app/docker/bootstrap_bi.py

RUN chmod 755 /app/docker/bootstrap.sh \
    && chown -R superset:superset /app/pythonpath /app/docker/bootstrap.sh /app/docker/bootstrap_bi.py

USER superset

ENTRYPOINT []
CMD ["bash", "/app/docker/bootstrap.sh"]
