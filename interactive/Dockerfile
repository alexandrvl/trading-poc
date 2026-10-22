FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends git gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY interactive/requirements.txt /app/interactive/requirements.txt
RUN pip install --no-cache-dir -r /app/interactive/requirements.txt

COPY interactive /app/interactive
COPY trading-dbt/init-scripts /opt/init-scripts
COPY trading-dbt/trading /opt/trading

ENV PYTHONPATH=/app
ENV DBT_PROJECT_DIR=/opt/trading
ENV SCHEMA_SQL=/opt/init-scripts/03-interactive.sql

EXPOSE 8000 8501

CMD ["uvicorn", "interactive.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
