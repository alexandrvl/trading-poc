"""Microbatch append into the repo Iceberg/MinIO catalog (pyiceberg SQL catalog)."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

TELEMETRY_SCHEMA_FIELDS = (
    ("telemetry_id", "long"),
    ("asset_id", "string"),
    ("event_ts", "timestamp"),
    ("active_power_kw", "double"),
    ("reactive_power_kvar", "double"),
    ("turbine_status", "string"),
    ("setpoint_limit_kw", "double"),
    ("control_mode", "string"),
    ("source_system", "string"),
    ("ingested_at", "timestamp"),
)

AFRR_SCHEMA_FIELDS = (
    ("activation_id", "long"),
    ("portfolio_id", "string"),
    ("asset_id", "string"),
    ("event_ts", "timestamp"),
    ("setpoint_kw", "double"),
    ("direction", "string"),
    ("price_eur_mwh", "double"),
    ("source_system", "string"),
)


class IcebergSink:
    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.enabled = bool(getattr(settings, "iceberg_enabled", True))
        self._lock = threading.Lock()
        self._telemetry: list[dict] = []
        self._afrr: list[dict] = []
        self._last_flush = time.monotonic()
        self._catalog = None
        self._tables: dict[str, Any] = {}
        self.last_flush: dict[str, Any] = {"status": "never", "rows": 0}
        self._id_seq = int(time.time() * 1000)

    def enqueue_telemetry(self, rows: list[dict]) -> None:
        if not self.enabled or not rows:
            return
        with self._lock:
            self._telemetry.extend(rows)

    def enqueue_afrr(self, rows: list[dict]) -> None:
        if not self.enabled or not rows:
            return
        with self._lock:
            self._afrr.extend(rows)

    def should_flush(self) -> bool:
        with self._lock:
            n = len(self._telemetry) + len(self._afrr)
            age = time.monotonic() - self._last_flush
        return n >= self.settings.iceberg_flush_rows or (
            n > 0 and age >= self.settings.iceberg_flush_seconds
        )

    def pending(self) -> int:
        with self._lock:
            return len(self._telemetry) + len(self._afrr)

    def flush(self) -> dict[str, Any]:
        with self._lock:
            telemetry = self._telemetry
            afrr = self._afrr
            self._telemetry = []
            self._afrr = []
            self._last_flush = time.monotonic()
        if not telemetry and not afrr:
            self.last_flush = {"status": "empty", "rows": 0}
            return self.last_flush
        try:
            tel_n = self._append("emsys_telemetry", TELEMETRY_SCHEMA_FIELDS, telemetry, partition_field="ingested_at")
            afr_n = self._append("afrr_activations", AFRR_SCHEMA_FIELDS, afrr, partition_field="event_ts")
            self.last_flush = {
                "status": "ok",
                "rows": tel_n + afr_n,
                "telemetry_rows": tel_n,
                "afrr_rows": afr_n,
                "flushed_at": datetime.now(timezone.utc).isoformat(),
            }
            logger.info("iceberg flush %s", self.last_flush)
            return self.last_flush
        except Exception as exc:
            logger.exception("iceberg flush failed")
            with self._lock:
                self._telemetry = telemetry + self._telemetry
                self._afrr = afrr + self._afrr
            self.last_flush = {"status": "error", "error": str(exc), "rows": 0}
            return self.last_flush

    def _next_id(self) -> int:
        self._id_seq += 1
        return self._id_seq

    def _catalog_handle(self):
        if self._catalog is not None:
            return self._catalog
        from pyiceberg.catalog import load_catalog

        endpoint = self.settings.s3_endpoint
        if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
            endpoint = f"http://{endpoint}"
        uri = (
            f"postgresql://{self.settings.pguser}:{self.settings.pgpassword}"
            f"@{self.settings.pghost}:{self.settings.pgport}/{self.settings.pgdatabase}"
        )
        warehouse = f"s3a://{self.settings.s3_bucket}/warehouse"
        self._catalog = load_catalog(
            "iceberg",
            **{
                "type": "sql",
                "uri": uri,
                "warehouse": warehouse,
                "s3.endpoint": endpoint,
                "s3.access-key-id": self.settings.s3_access_key,
                "s3.secret-access-key": self.settings.s3_secret_key,
                "s3.path-style-access": "true",
                "s3.region": self.settings.s3_region,
            },
        )
        self._catalog.create_namespace_if_not_exists(self.settings.iceberg_namespace)
        return self._catalog

    def _table(self, name: str, fields: tuple, partition_field: str):
        if name in self._tables:
            return self._tables[name]
        from pyiceberg.partitioning import PartitionField, PartitionSpec
        from pyiceberg.schema import NestedField, Schema
        from pyiceberg.transforms import DayTransform
        from pyiceberg.types import DoubleType, LongType, StringType, TimestampType

        type_map = {
            "long": LongType(),
            "string": StringType(),
            "double": DoubleType(),
            "timestamp": TimestampType(),
        }
        nested = [
            NestedField(i, fname, type_map[ftype], required=False)
            for i, (fname, ftype) in enumerate(fields, start=1)
        ]
        schema = Schema(*nested)
        source_id = next(i for i, (fname, _) in enumerate(fields, start=1) if fname == partition_field)
        spec = PartitionSpec(
            PartitionField(source_id=source_id, field_id=1000, transform=DayTransform(), name=f"day_{partition_field}")
        )
        catalog = self._catalog_handle()
        ident = (self.settings.iceberg_namespace, name)
        location = (
            f"s3a://{self.settings.s3_bucket}/warehouse/"
            f"{self.settings.iceberg_namespace}.db/{name}"
        )
        try:
            table = catalog.load_table(ident)
        except Exception:
            table = catalog.create_table(
                identifier=ident,
                schema=schema,
                location=location,
                partition_spec=spec,
                properties={
                    "write.format.default": "parquet",
                    "write.parquet.compression-codec": "zstd",
                    "write.distribution-mode": "hash",
                },
            )
        self._tables[name] = table
        return table

    def _append(self, name: str, fields: tuple, rows: list[dict], partition_field: str) -> int:
        if not rows:
            return 0
        import pyarrow as pa

        table = self._table(name, fields, partition_field)
        payload: dict[str, list] = {fname: [] for fname, _ in fields}
        for row in rows:
            for fname, ftype in fields:
                val = row.get(fname)
                if val is None and fname.endswith("_id") and ftype == "long":
                    val = self._next_id()
                if isinstance(val, datetime):
                    val = val.replace(tzinfo=None)
                payload[fname].append(val)
        arrays = {}
        for fname, ftype in fields:
            if ftype == "timestamp":
                arrays[fname] = pa.array(payload[fname], type=pa.timestamp("us"))
            elif ftype == "long":
                arrays[fname] = pa.array(payload[fname], type=pa.int64())
            elif ftype == "double":
                arrays[fname] = pa.array(payload[fname], type=pa.float64())
            else:
                arrays[fname] = pa.array(payload[fname], type=pa.string())
        table.append(pa.table(arrays))
        self._tables.pop(name, None)
        return len(rows)

    def maintain(self) -> dict[str, Any]:
        results = {}
        for name in ("emsys_telemetry", "afrr_activations"):
            try:
                table = self._tables.get(name) or self._table(
                    name,
                    TELEMETRY_SCHEMA_FIELDS if name == "emsys_telemetry" else AFRR_SCHEMA_FIELDS,
                    "ingested_at" if name == "emsys_telemetry" else "event_ts",
                )
                expire = getattr(table, "expire_snapshots", None)
                if callable(expire):
                    expire(retain_last=5)
                results[name] = "ok"
            except Exception as exc:
                results[name] = str(exc)
        return results
