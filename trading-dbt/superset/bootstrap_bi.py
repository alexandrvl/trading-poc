"""Publish the information marts as a Superset dashboard.

Safe to run on every container start: the database, datasets, charts, and
dashboard are replaced in place. Chart data is a live query (cache_timeout -1);
the dashboard polls on DASHBOARD_REFRESH_SECONDS. No REST rebuild.
"""

from __future__ import annotations

import json
import logging
import time

from flask import g
from sqlalchemy import text

from live_refresh import (
    CHART_CACHE_TIMEOUT,
    DASHBOARD_REFRESH_SECONDS,
    MART_SCHEMA,
    WAREHOUSE_NAME,
    WAREHOUSE_URI,
)

log = logging.getLogger("bootstrap_bi")

DATABASE_NAME = WAREHOUSE_NAME
DASHBOARD_SLUG = "asset-internal-billing"
SCHEMA = MART_SCHEMA

DATASETS = {
    "mart_asset_internal_billing": (
        "Asset bill: wholesale allocation, imbalance, reserves, curtailment, and net revenue."
    ),
    "mart_curtailment_compensation": (
        "Intervals where external control reduced output below the intraday forecast."
    ),
    "mart_portfolio_reconciliation": (
        "Portfolio settlement compared with the sum of the asset bills."
    ),
}

CHART_NAMES = [
    "Net revenue",
    "Imbalance cost",
    "Curtailment compensation",
    "Net revenue by asset",
    "Net revenue by interval",
    "Revenue components by asset",
    "Portfolio reconciliation",
    "Curtailment intervals",
]


def metric(column: str, label: str, aggregate: str = "SUM") -> dict:
    return {
        "expressionType": "SIMPLE",
        "column": {"column_name": column},
        "aggregate": aggregate,
        "label": label,
        "optionName": f"metric_{column}_{aggregate}".lower(),
    }


def wait_for_marts(database) -> None:
    last_error: Exception | None = None
    statement = text(
        f"SELECT count(*) FROM {SCHEMA}.mart_asset_internal_billing"
    )
    for attempt in range(1, 121):
        try:
            with database.get_sqla_engine() as engine:
                with engine.connect() as conn:
                    count = conn.execute(statement).scalar()
            log.info("billing mart is queryable (%s rows)", count)
            if not count:
                raise RuntimeError("mart_asset_internal_billing is empty")
            return
        except Exception as exc:  # noqa: BLE001 - Trino or dbt may still be starting
            last_error = exc
            if attempt == 1 or attempt % 10 == 0:
                log.info("waiting for marts (%s): %s", attempt, exc)
            time.sleep(5)
    raise RuntimeError(f"information marts are not queryable: {last_error}")


def upsert_database(session, database_model):
    database = (
        session.query(database_model).filter_by(database_name=DATABASE_NAME).one_or_none()
    )
    if database is None:
        database = database_model(database_name=DATABASE_NAME, sqlalchemy_uri=WAREHOUSE_URI)
        session.add(database)
    database.sqlalchemy_uri = WAREHOUSE_URI
    database.cache_timeout = CHART_CACHE_TIMEOUT
    database.expose_in_sqllab = True
    database.allow_run_async = False
    database.allow_ctas = False
    database.allow_cvas = False
    database.allow_dml = False
    engine_params = {}
    if WAREHOUSE_URI.startswith("trino"):
        engine_params = {"connect_args": {"source": "superset"}}
    database.extra = json.dumps(
        {
            "metadata_params": {},
            "engine_params": engine_params,
            "metadata_cache_timeout": {},
            "schemas_allowed_for_file_upload": [],
        }
    )
    session.commit()
    return database


def upsert_dataset(session, table_model, database, table_name: str, description: str, admin):
    dataset = (
        session.query(table_model)
        .filter_by(database_id=database.id, schema=SCHEMA, table_name=table_name)
        .one_or_none()
    )
    if dataset is None:
        dataset = table_model(
            table_name=table_name,
            schema=SCHEMA,
            database=database,
        )
        session.add(dataset)
        session.commit()
    dataset.description = description
    dataset.owners = [admin]
    dataset.cache_timeout = CHART_CACHE_TIMEOUT
    dataset.fetch_metadata()
    for column in dataset.columns:
        if column.column_name in {"interval_start", "interval_end"}:
            column.is_dttm = True
    dataset.main_dttm_col = "interval_start"
    session.commit()
    if not dataset.columns:
        raise RuntimeError(f"{table_name} has no columns after metadata sync")
    log.info("dataset %s.%s (%s columns)", SCHEMA, table_name, len(dataset.columns))
    return dataset


def form_data(dataset, viz_type: str, **extra) -> dict:
    payload = {
        "datasource": f"{dataset.id}__table",
        "viz_type": viz_type,
        "adhoc_filters": [],
        "row_limit": 1000,
        "extra_form_data": {},
    }
    payload.update(extra)
    return payload


def query_context(dataset, form: dict, columns: list, metrics: list) -> dict:
    return {
        "datasource": {"id": dataset.id, "type": "table"},
        "force": False,
        "queries": [
            {
                "filters": [],
                "extras": {"having": "", "where": ""},
                "applied_time_extras": {},
                "columns": columns,
                "metrics": metrics,
                "annotation_layers": [],
                "row_limit": form.get("row_limit", 1000),
                "series_limit": 0,
                "order_desc": True,
                "url_params": {},
                "custom_params": {},
                "custom_form_data": {},
                "time_offsets": [],
                "post_processing": [],
            }
        ],
        "form_data": form,
        "result_format": "json",
        "result_type": "full",
    }


def add_chart(session, slice_model, admin, name: str, dataset, viz_type: str, form: dict, columns: list, metrics: list):
    chart = slice_model(
        slice_name=name,
        datasource_id=dataset.id,
        datasource_type="table",
        viz_type=viz_type,
        params="{}",
    )
    chart.owners = [admin]
    chart.cache_timeout = CHART_CACHE_TIMEOUT
    session.add(chart)
    session.flush()
    form["slice_id"] = chart.id
    chart.params = json.dumps(form)
    chart.query_context = json.dumps(query_context(dataset, form, columns, metrics))
    return chart


def chart_node(chart, width: int, height: int, parents: list[str]) -> tuple[str, dict]:
    key = f"CHART-{chart.id}"
    return key, {
        "type": "CHART",
        "id": key,
        "children": [],
        "parents": parents,
        "meta": {
            "chartId": chart.id,
            "height": height,
            "width": width,
            "sliceName": chart.slice_name,
        },
    }


def row_node(row_id: str, children: list[str]) -> dict:
    return {
        "type": "ROW",
        "id": row_id,
        "children": children,
        "parents": ["ROOT_ID", "GRID_ID"],
        "meta": {"background": "BACKGROUND_TRANSPARENT"},
    }


def build_dashboard(session, models, admin, datasets):
    existing = session.query(models["Dashboard"]).filter_by(slug=DASHBOARD_SLUG).one_or_none()
    if existing is not None:
        session.delete(existing)
        session.commit()
    for chart in session.query(models["Slice"]).filter(models["Slice"].slice_name.in_(CHART_NAMES)).all():
        session.delete(chart)
    session.commit()

    billing = datasets["mart_asset_internal_billing"]
    curtailment = datasets["mart_curtailment_compensation"]
    reconciliation = datasets["mart_portfolio_reconciliation"]

    net = metric("net_revenue_eur", "Net revenue EUR")
    imbalance = metric("imbalance_cost_eur", "Imbalance cost EUR")
    compensation = metric("curtailment_compensation_eur", "Curtailment compensation EUR")
    allocated = metric("allocated_revenue_eur", "Allocated revenue EUR")

    created = {
        "Net revenue": add_chart(
            session, models["Slice"], admin, "Net revenue", billing, "big_number_total",
            form_data(billing, "big_number_total", metric=net, y_axis_format=",.2f", subheader="EUR"),
            [], [net],
        ),
        "Imbalance cost": add_chart(
            session, models["Slice"], admin, "Imbalance cost", billing, "big_number_total",
            form_data(billing, "big_number_total", metric=imbalance, y_axis_format=",.2f", subheader="EUR"),
            [], [imbalance],
        ),
        "Curtailment compensation": add_chart(
            session, models["Slice"], admin, "Curtailment compensation", billing, "big_number_total",
            form_data(billing, "big_number_total", metric=compensation, y_axis_format=",.2f", subheader="EUR"),
            [], [compensation],
        ),
        "Net revenue by asset": add_chart(
            session, models["Slice"], admin, "Net revenue by asset", billing, "echarts_timeseries_bar",
            form_data(
                billing, "echarts_timeseries_bar",
                x_axis="asset_id", metrics=[net], groupby=[],
                y_axis_format=",.2f", show_legend=False, rich_tooltip=True,
            ),
            ["asset_id"], [net],
        ),
        "Net revenue by interval": add_chart(
            session, models["Slice"], admin, "Net revenue by interval", billing, "echarts_timeseries_bar",
            form_data(
                billing, "echarts_timeseries_bar",
                x_axis="interval_start", metrics=[net], groupby=["asset_id"],
                y_axis_format=",.2f", show_legend=True, rich_tooltip=True,
                x_axis_time_format="%H:%M",
            ),
            ["interval_start", "asset_id"], [net],
        ),
        "Revenue components by asset": add_chart(
            session, models["Slice"], admin, "Revenue components by asset", billing, "echarts_timeseries_bar",
            form_data(
                billing, "echarts_timeseries_bar",
                x_axis="asset_id",
                metrics=[allocated, imbalance, compensation],
                groupby=[],
                y_axis_format=",.2f", show_legend=True, rich_tooltip=True,
            ),
            ["asset_id"], [allocated, imbalance, compensation],
        ),
        "Portfolio reconciliation": add_chart(
            session, models["Slice"], admin, "Portfolio reconciliation", reconciliation, "table",
            form_data(
                reconciliation, "table",
                query_mode="raw",
                all_columns=[
                    "portfolio_id", "interval_start", "generation_mwh",
                    "allocated_revenue_eur", "portfolio_revenue_eur",
                    "imbalance_cost_eur", "portfolio_imbalance_cost_eur",
                    "curtailment_compensation_eur", "net_revenue_eur",
                ],
                include_search=True,
                show_cell_bars=True,
                table_timestamp_format="%Y-%m-%d %H:%M",
            ),
            [
                "portfolio_id", "interval_start", "generation_mwh",
                "allocated_revenue_eur", "portfolio_revenue_eur",
                "imbalance_cost_eur", "portfolio_imbalance_cost_eur",
                "curtailment_compensation_eur", "net_revenue_eur",
            ],
            [],
        ),
        "Curtailment intervals": add_chart(
            session, models["Slice"], admin, "Curtailment intervals", curtailment, "table",
            form_data(
                curtailment, "table",
                query_mode="raw",
                all_columns=[
                    "asset_id", "portfolio_id", "interval_start",
                    "actual_mwh", "baseline_mwh", "lost_energy_mwh",
                    "clearing_price_eur_mwh", "compensation_eur",
                ],
                include_search=True,
                show_cell_bars=True,
                table_timestamp_format="%Y-%m-%d %H:%M",
            ),
            [
                "asset_id", "portfolio_id", "interval_start",
                "actual_mwh", "baseline_mwh", "lost_energy_mwh",
                "clearing_price_eur_mwh", "compensation_eur",
            ],
            [],
        ),
    }

    layout_rows = [
        ("ROW-kpis", [
            ("Net revenue", 4, 22),
            ("Imbalance cost", 4, 22),
            ("Curtailment compensation", 4, 22),
        ]),
        ("ROW-trend", [
            ("Net revenue by interval", 8, 50),
            ("Net revenue by asset", 4, 50),
        ]),
        ("ROW-components", [
            ("Revenue components by asset", 12, 50),
        ]),
        ("ROW-tables", [
            ("Portfolio reconciliation", 7, 56),
            ("Curtailment intervals", 5, 56),
        ]),
    ]

    position: dict = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {
            "type": "GRID",
            "id": "GRID_ID",
            "children": ["ROW-intro", *[row_id for row_id, _ in layout_rows]],
            "parents": ["ROOT_ID"],
        },
        "HEADER_ID": {
            "type": "HEADER",
            "id": "HEADER_ID",
            "meta": {"text": "Asset internal billing"},
        },
        "ROW-intro": row_node("ROW-intro", ["MARKDOWN-intro"]),
        "MARKDOWN-intro": {
            "type": "MARKDOWN",
            "id": "MARKDOWN-intro",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", "ROW-intro"],
            "meta": {
                "width": 12,
                "height": 24,
                "code": (
                    "### How an asset is billed\n\n"
                    "Wholesale revenue is split by generation. Imbalance is charged only "
                    "to assets whose forecast error has the same sign as the portfolio. "
                    "Curtailment compensation uses the intraday downscale and the mFRR down price.\n\n"
                    "The sample afternoon is **2026-06-01 12:00–14:00**. At 12:00, "
                    "**WT-EE-N-02** carries the Wind_EE_North imbalance. "
                    "**WT-EE-N-01** is curtailed from 13:00 to 13:30."
                ),
            },
        },
    }
    ordered_charts = []
    for row_id, items in layout_rows:
        keys = []
        for name, width, height in items:
            key, node = chart_node(created[name], width, height, ["ROOT_ID", "GRID_ID", row_id])
            position[key] = node
            keys.append(key)
            ordered_charts.append(created[name])
        position[row_id] = row_node(row_id, keys)

    chart_ids = [chart.id for chart in ordered_charts]
    dashboard = models["Dashboard"](
        dashboard_title="Asset internal billing",
        slug=DASHBOARD_SLUG,
        published=True,
        position_json=json.dumps(position),
        json_metadata=json.dumps(
            {
                "native_filter_configuration": [
                    {
                        "id": "NATIVE_FILTER-PORTFOLIO",
                        "name": "Portfolio",
                        "filterType": "filter_select",
                        "targets": [
                            {"datasetId": billing.id, "column": {"name": "portfolio_id"}}
                        ],
                        "defaultDataMask": {
                            "extraFormData": {},
                            "filterState": {},
                            "ownState": {},
                        },
                        "controlValues": {
                            "enableEmptyFilter": False,
                            "defaultToFirstItem": False,
                            "multiSelect": True,
                            "searchAllOptions": False,
                            "inverseSelection": False,
                        },
                        "cascadeParentIds": [],
                        "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                        "type": "NATIVE_FILTER",
                        "description": "Limit charts to one or more portfolios",
                        "chartsInScope": chart_ids,
                        "tabsInScope": [],
                    }
                ],
                "chart_configuration": {},
                "global_chart_configuration": {
                    "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                    "chartsInScope": chart_ids,
                },
                "refresh_frequency": DASHBOARD_REFRESH_SECONDS,
                "timed_refresh_immune_slices": [],
                "expanded_slices": {},
                "label_colors": {},
                "shared_label_colors": {},
                "color_scheme": "",
                "cross_filters_enabled": True,
            }
        ),
    )
    dashboard.owners = [admin]
    dashboard.slices = ordered_charts
    session.add(dashboard)
    session.commit()
    log.info("dashboard /superset/dashboard/%s/ id=%s", dashboard.slug, dashboard.id)
    return dashboard


def verify_charts(charts) -> None:
    from superset.commands.chart.data.get_data_command import ChartDataCommand
    from superset.common.query_context_factory import QueryContextFactory

    factory = QueryContextFactory()
    for chart in charts:
        payload = json.loads(chart.query_context)
        try:
            context = factory.create(
                datasource=payload["datasource"],
                queries=payload["queries"],
                form_data=payload["form_data"],
            )
            result = ChartDataCommand(context).run()
        except Exception as exc:  # noqa: BLE001 - printed so the server can still start
            log.error("chart %s failed: %s", chart.slice_name, exc)
            continue
        rows = result["queries"][0].get("data") or []
        log.info("chart %s returned %s rows; sample=%s", chart.slice_name, len(rows), rows[:1])
        if not rows:
            log.error("chart %s returned no rows", chart.slice_name)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    from superset.app import create_app

    app = create_app()
    with app.app_context():
        from superset import security_manager
        from superset.connectors.sqla.models import SqlaTable
        from superset.extensions import db
        from superset.models.core import Database
        from superset.models.dashboard import Dashboard
        from superset.models.slice import Slice

        admin = security_manager.find_user(username="admin")
        if admin is None:
            raise RuntimeError("admin user is missing; fab create-admin did not run")
        g.user = admin

        models = {"Database": Database, "Dashboard": Dashboard, "Slice": Slice}
        database = upsert_database(db.session, Database)
        wait_for_marts(database)
        datasets = {
            name: upsert_dataset(db.session, SqlaTable, database, name, description, admin)
            for name, description in DATASETS.items()
        }
        dashboard = build_dashboard(db.session, models, admin, datasets)
        verify_charts(list(dashboard.slices))


if __name__ == "__main__":
    main()
