"""
Generic Data Loader Framework for Iceberg

This module provides a flexible, configuration-driven framework for loading data
from various sources (PostgreSQL, MySQL, etc.) into Apache Iceberg tables.

Key Features:
- Abstract base classes for extensibility
- Configuration-driven table definitions
- Pluggable data sources
- State management for incremental loads
- Support for both fact and dimension tables
"""

import os
import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum

import duckdb
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.types import (
    NestedField, StringType, IntegerType, DecimalType,
    TimestampType, DateType, BooleanType, LongType, FloatType, DoubleType
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Configuration Data Classes
# ============================================================================

@dataclass
class DatabaseConfig:
    """Base configuration for database connections and storage"""
    # Source database
    source_type: str = "postgresql"  # postgresql, mysql, etc.
    source_host: str = os.getenv("SOURCE_HOST", "postgres")
    source_port: int = int(os.getenv("SOURCE_PORT", "5432"))
    source_db: str = os.getenv("SOURCE_DB", "iceberg_dbt")
    source_user: str = os.getenv("SOURCE_USER", "dbt_user")
    source_password: str = os.getenv("SOURCE_PASSWORD", "dbt_password")
    source_schema: str = os.getenv("SOURCE_SCHEMA", "trading")

    # Object storage (S3/MinIO)
    s3_endpoint: str = os.getenv("S3_ENDPOINT", "minio:9000")
    s3_access_key: str = os.getenv("S3_ACCESS_KEY", "minioadmin")
    s3_secret_key: str = os.getenv("S3_SECRET_KEY", "minioadmin")
    s3_bucket: str = os.getenv("S3_BUCKET", "meter-data")
    s3_region: str = os.getenv("S3_REGION", "us-east-1")

    # Iceberg catalog
    catalog_type: str = "sql"  # sql, rest, hive
    iceberg_namespace: str = "raw"


class FieldType(Enum):
    """Supported field types for schema definition"""
    STRING = "string"
    INTEGER = "integer"
    LONG = "long"
    FLOAT = "float"
    DOUBLE = "double"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    TIMESTAMP = "timestamp"


@dataclass
class FieldDefinition:
    """Definition for a table field"""
    name: str
    type: FieldType
    precision: Optional[int] = None  # For decimal
    scale: Optional[int] = None  # For decimal
    required: bool = False


@dataclass
class TableDefinition:
    """Complete table definition for loading"""
    name: str
    fields: List[FieldDefinition]
    source_query: Optional[str] = None  # If None, will be generated
    partition_field: Optional[str] = None  # For partitioned tables
    is_incremental: bool = False
    incremental_field: Optional[str] = None  # e.g., 'creation_time'
    primary_key: Optional[str] = None


# ============================================================================
# Abstract Base Classes
# ============================================================================

class StateManagerInterface(ABC):
    """Interface for managing incremental load state"""

    @abstractmethod
    def get_state(self) -> Dict[str, Any]:
        """Retrieve current state"""
        pass

    @abstractmethod
    def save_state(self, state: Dict[str, Any]) -> None:
        """Persist state"""
        pass

    @abstractmethod
    def get_last_processed_value(self, table_name: str, field_name: str) -> Tuple[Any, Dict]:
        """Get last processed value for incremental loads"""
        pass


class DataSourceInterface(ABC):
    """Interface for different data source types"""

    @abstractmethod
    def connect(self) -> Any:
        """Establish connection to data source"""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to data source"""
        pass

    @abstractmethod
    def get_scanner_extension(self) -> str:
        """Return DuckDB scanner extension name"""
        pass

    @abstractmethod
    def get_connection_string(self) -> str:
        """Return connection string for DuckDB attach"""
        pass


# ============================================================================
# Concrete Implementations - State Management
# ============================================================================

class S3StateManager(StateManagerInterface):
    """S3-based state manager for incremental loads"""

    def __init__(self, connection, bucket: str, state_file: str = "state.json"):
        self.connection = connection
        self.bucket = bucket
        self.state_file = state_file
        self.state_path = f"s3://{bucket}/{state_file}"

    def get_state(self) -> Dict[str, Any]:
        """Retrieve state from S3"""
        try:
            result = self.connection.execute(
                f"SELECT * FROM read_json('{self.state_path}');"
            ).fetchone()

            if result:
                return json.loads(result[0]) if isinstance(result[0], str) else dict(result)
            return {}
        except Exception as e:
            logger.warning(f"No existing state found: {e}")
            return {}

    def save_state(self, state: Dict[str, Any]) -> None:
        """Save state to S3"""
        try:
            state_json = json.dumps(state)
            self.connection.execute(f"""
                COPY (SELECT '{state_json}' as state)
                TO '{self.state_path}' (FORMAT JSON);
            """)
            logger.info(f"State saved to {self.state_path}")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            raise

    def get_last_processed_value(self, table_name: str, field_name: str) -> Tuple[Any, Dict]:
        """Get last processed value for a specific table/field"""
        state = self.get_state()

        # Support both new and legacy state formats
        table_state_key = f"{table_name}_window"

        if table_state_key in state:
            last_value = state[table_state_key].get('end', '1900-01-01 00:00:00')
        elif table_name in state:
            last_value = state[table_name].get(field_name, '1900-01-01 00:00:00')
        else:
            last_value = '1900-01-01 00:00:00'

        logger.info(f"Last processed {field_name} for {table_name}: {last_value}")
        return last_value, state


# ============================================================================
# Concrete Implementations - Data Sources
# ============================================================================

class PostgreSQLDataSource(DataSourceInterface):
    """PostgreSQL data source implementation"""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.connection = None

    def connect(self) -> duckdb.DuckDBPyConnection:
        """Connect to PostgreSQL via DuckDB"""
        self.connection = duckdb.connect(":memory:")

        # Load extensions
        self.connection.execute("INSTALL postgres_scanner; LOAD postgres_scanner;")
        self.connection.execute("INSTALL httpfs; LOAD httpfs;")

        # Attach PostgreSQL
        conn_str = self.get_connection_string()
        self.connection.execute(f"ATTACH '{conn_str}' AS raw (TYPE postgres);")
        self.connection.execute("USE raw;")

        # Configure S3
        s3_config = f"""
            SET s3_region='{self.config.s3_region}';
            SET s3_access_key_id='{self.config.s3_access_key}';
            SET s3_secret_access_key='{self.config.s3_secret_key}';
            SET s3_endpoint='{self.config.s3_endpoint}';
            SET s3_url_style='path';
            SET s3_use_ssl=false;
        """
        self.connection.execute(s3_config)

        return self.connection

    def disconnect(self) -> None:
        """Close connection"""
        if self.connection:
            self.connection.close()

    def get_scanner_extension(self) -> str:
        return "postgres_scanner"

    def get_connection_string(self) -> str:
        return (
            f"host={self.config.source_host} "
            f"port={self.config.source_port} "
            f"dbname={self.config.source_db} "
            f"user={self.config.source_user} "
            f"password={self.config.source_password}"
        )


# ============================================================================
# Schema Conversion
# ============================================================================

class SchemaConverter:
    """Convert table definitions to Iceberg schemas"""

    @staticmethod
    def field_type_to_iceberg(field_type: FieldType, precision: int = None, scale: int = None):
        """Convert FieldType to Iceberg type"""
        type_map = {
            FieldType.STRING: StringType(),
            FieldType.INTEGER: IntegerType(),
            FieldType.LONG: LongType(),
            FieldType.FLOAT: FloatType(),
            FieldType.DOUBLE: DoubleType(),
            FieldType.BOOLEAN: BooleanType(),
            FieldType.DATE: DateType(),
            FieldType.TIMESTAMP: TimestampType(),
        }

        if field_type == FieldType.DECIMAL:
            return DecimalType(precision or 15, scale or 3)

        return type_map.get(field_type, StringType())

    @staticmethod
    def table_definition_to_schema(table_def: TableDefinition) -> Schema:
        """Convert TableDefinition to Iceberg Schema

        Note: All fields are marked as optional (required=False) to match
        DuckDB's Parquet export behavior, which always creates nullable columns.
        """
        fields = []
        for idx, field in enumerate(table_def.fields, start=1):
            iceberg_type = SchemaConverter.field_type_to_iceberg(
                field.type, field.precision, field.scale
            )
            fields.append(NestedField(
                field_id=idx,
                name=field.name,
                field_type=iceberg_type,
                required=False  # Always False to match Parquet nullable columns
            ))

        return Schema(*fields)

    @staticmethod
    def generate_source_query(table_def: TableDefinition, source_schema: str) -> str:
        """Generate default SQL query for table extraction"""
        if table_def.source_query:
            return table_def.source_query

        field_names = [f.name for f in table_def.fields]
        fields_str = ",\n                ".join(field_names)

        query = f"""
            SELECT
                {fields_str}
            FROM {source_schema}.{table_def.name}
        """

        # Add ordering if there's a primary key
        if table_def.primary_key:
            query += f"\n            ORDER BY {table_def.primary_key}"

        return query


# ============================================================================
# Iceberg Table Manager
# ============================================================================

class IcebergTableManager:
    """Manages Iceberg table creation and data loading"""

    def __init__(self, config: DatabaseConfig, data_source: DataSourceInterface):
        self.config = config
        self.data_source = data_source
        self._catalog = None

    def _get_catalog(self):
        """Lazy load Iceberg catalog"""
        if self._catalog:
            return self._catalog

        try:
            bucket_name = self.config.s3_bucket

            # Catalog URI (for SQL catalog type)
            uri = (
                f"postgresql://{self.config.source_user}:{self.config.source_password}"
                f"@{self.config.source_host}:{self.config.source_port}/{self.config.source_db}"
            )

            endpoint = self.config.s3_endpoint
            if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
                endpoint = f"http://{endpoint}"

            warehouse = f"s3a://{bucket_name}/warehouse"
            logger.info(f"Initializing Iceberg catalog with warehouse: {warehouse}")

            self._catalog = load_catalog(
                "iceberg",
                **{
                    "type": self.config.catalog_type,
                    "uri": uri,
                    "warehouse": warehouse,
                    "s3.endpoint": endpoint,
                    "s3.access-key-id": self.config.s3_access_key,
                    "s3.secret-access-key": self.config.s3_secret_key,
                    "s3.path-style-access": "true",
                    "s3.region": self.config.s3_region
                }
            )
            return self._catalog
        except Exception as e:
            logger.error(f"Failed to load Iceberg catalog: {e}")
            raise

    def create_or_get_table(self, table_def: TableDefinition, schema: Schema):
        """Create or retrieve existing Iceberg table"""
        catalog = self._get_catalog()
        catalog.create_namespace_if_not_exists(self.config.iceberg_namespace)

        table_location = (
            f"s3a://{self.config.s3_bucket}/warehouse/"
            f"{self.config.iceberg_namespace}.db/{table_def.name}"
        )

        try:
            table = catalog.create_table_if_not_exists(
                identifier=(self.config.iceberg_namespace, table_def.name),
                schema=schema,
                location=table_location,
                properties={"write.format.default": "parquet"},
            )
            logger.info(f"Table ready: {self.config.iceberg_namespace}.{table_def.name}")
            return table
        except Exception as e:
            logger.error(f"Failed to create table {table_def.name}: {e}")
            raise

    @staticmethod
    def get_existing_files(table) -> set:
        """Get set of data files already in the table"""
        existing = set()
        try:
            scan = table.scan()
            for task in scan.plan_files():
                existing.add(task.file.file_path)
            logger.info(f"Found {len(existing)} existing files in table")
        except Exception as e:
            logger.warning(f"Could not scan existing files: {e}")
        return existing

    def load_table(self, table_def: TableDefinition, connection) -> None:
        """Load a table from source to Iceberg"""
        logger.info(f"{'='*80}")
        logger.info(f"Loading table: {table_def.name}")
        logger.info(f"{'='*80}")

        # Convert table definition to Iceberg schema
        schema = SchemaConverter.table_definition_to_schema(table_def)

        # Create or get table
        table = self.create_or_get_table(table_def, schema)

        # Generate query
        query = SchemaConverter.generate_source_query(table_def, self.config.source_schema)

        # Export to S3
        output_path = f"s3://{self.config.s3_bucket}/{table_def.name}/{uuid.uuid4()}-{table_def.name}.parquet"

        if table_def.partition_field:
            # Partitioned export
            output_path = f"s3://{self.config.s3_bucket}/{table_def.name}/{table_def.partition_field}=*/*.parquet"
            logger.info(f"Exporting partitioned data to {output_path}")
        else:
            logger.info(f"Exporting data to {output_path}")

        connection.execute(f"""
            COPY ({query}) TO '{output_path}' (FORMAT PARQUET)
        """)

        # Get files and add to table
        result = connection.sql(f"""
            SELECT distinct filename FROM read_parquet('{output_path}', filename = true);
        """).fetchall()
        files = [row[0] for row in result]

        existing = self.get_existing_files(table)
        new_files = [f for f in files if f not in existing]

        if new_files:
            logger.info(f"Adding {len(new_files)} new files to Iceberg table")
            table.add_files(new_files)
        else:
            logger.info(f"No new files to add (table up to date)")


# ============================================================================
# Data Loader Orchestrator
# ============================================================================

class GenericDataLoader:
    """Main orchestrator for loading data to Iceberg"""

    def __init__(
        self,
        config: DatabaseConfig,
        data_source: DataSourceInterface,
        table_definitions: List[TableDefinition],
        state_manager: Optional[StateManagerInterface] = None
    ):
        self.config = config
        self.data_source = data_source
        self.table_definitions = table_definitions
        self.state_manager = state_manager
        self.table_manager = IcebergTableManager(config, data_source)

    def load_all_tables(self) -> None:
        """Load all defined tables"""
        connection = None
        try:
            connection = self.data_source.connect()

            failures = []
            for table_def in self.table_definitions:
                try:
                    self.table_manager.load_table(table_def, connection)
                except Exception as e:
                    logger.error(f"Failed to load table {table_def.name}: {e}")
                    failures.append(table_def.name)

            logger.info(f"{'='*80}")
            logger.info("Data loading complete!")
            logger.info(f"Loaded tables: {[t.name for t in self.table_definitions if t.name not in failures]}")
            logger.info(f"{'='*80}")
            if failures:
                raise RuntimeError(f"Failed to load tables: {failures}")

        finally:
            if connection:
                self.data_source.disconnect()


# ============================================================================
# Configuration from YAML/JSON (Optional Extension Point)
# ============================================================================

class ConfigLoader:
    """Load table definitions from configuration files"""

    @staticmethod
    def from_dict(config: Dict[str, Any]) -> List[TableDefinition]:
        """Convert dictionary config to TableDefinition list"""
        tables = []

        for table_config in config.get('tables', []):
            fields = []
            for field_config in table_config.get('fields', []):
                field = FieldDefinition(
                    name=field_config['name'],
                    type=FieldType(field_config['type']),
                    precision=field_config.get('precision'),
                    scale=field_config.get('scale'),
                    required=field_config.get('required', False)
                )
                fields.append(field)

            table_def = TableDefinition(
                name=table_config['name'],
                fields=fields,
                source_query=table_config.get('source_query'),
                partition_field=table_config.get('partition_field'),
                is_incremental=table_config.get('is_incremental', False),
                incremental_field=table_config.get('incremental_field'),
                primary_key=table_config.get('primary_key')
            )
            tables.append(table_def)

        return tables


# ============================================================================
# Example Usage
# ============================================================================

def _fields(*specs) -> List[FieldDefinition]:
    """Build field definitions from (name, type) or (name, type, kwargs) tuples."""
    fields = []
    for spec in specs:
        name, field_type = spec[0], spec[1]
        extra = spec[2] if len(spec) > 2 else {}
        fields.append(FieldDefinition(name, field_type, **extra))
    return fields


def create_trading_definitions() -> List[TableDefinition]:
    """Source tables for the electricity-trading Data Vault."""
    string, timestamp, double, integer, long = (
        FieldType.STRING,
        FieldType.TIMESTAMP,
        FieldType.DOUBLE,
        FieldType.INTEGER,
        FieldType.LONG,
    )

    assets = TableDefinition(
        name="assets",
        primary_key="asset_id",
        fields=_fields(
            ("asset_id", string),
            ("asset_name", string),
            ("technology", string),
            ("nominal_power_kw", double),
            ("latitude", double),
            ("longitude", double),
            ("zone_code", string),
            ("turbine_model", string),
            ("commissioning_date", timestamp),
            ("last_modified", timestamp),
            ("source_system", string),
        ),
    )
    portfolios = TableDefinition(
        name="portfolios",
        primary_key="portfolio_id",
        fields=_fields(
            ("portfolio_id", string),
            ("portfolio_name", string),
            ("bidding_zone", string),
            ("strategy_module", string),
            ("status", string),
            ("valid_from", timestamp),
            ("last_modified", timestamp),
            ("source_system", string),
        ),
    )
    membership = TableDefinition(
        name="portfolio_membership",
        primary_key="portfolio_id, asset_id, valid_from",
        fields=_fields(
            ("portfolio_id", string),
            ("asset_id", string),
            ("valid_from", timestamp),
            ("valid_to", timestamp),
            ("membership_share", double),
            ("last_modified", timestamp),
            ("source_system", string),
        ),
    )
    markets = TableDefinition(
        name="markets",
        primary_key="market_code",
        fields=_fields(
            ("market_code", string),
            ("market_name", string),
            ("segment", string),
            ("product_resolution_min", integer),
            ("tso", string),
            ("currency_code", string),
            ("source_system", string),
        ),
    )
    orders = TableDefinition(
        name="trade_orders",
        primary_key="order_id",
        fields=_fields(
            ("order_id", string),
            ("portfolio_id", string),
            ("market_code", string),
            ("price_eur", double),
            ("volume_mw", double),
            ("delivery_start", timestamp),
            ("delivery_end", timestamp),
            ("order_type", string),
            ("direction", string),
            ("order_status", string),
            ("trade_ts", timestamp),
            ("source_system", string),
        ),
    )
    telemetry = TableDefinition(
        name="emsys_telemetry",
        is_incremental=True,
        incremental_field="ingested_at",
        fields=_fields(
            ("telemetry_id", long),
            ("asset_id", string),
            ("event_ts", timestamp),
            ("active_power_kw", double),
            ("reactive_power_kvar", double),
            ("turbine_status", string),
            ("setpoint_limit_kw", double),
            ("control_mode", string),
            ("source_system", string),
            ("ingested_at", timestamp),
        ),
    )
    capacity = TableDefinition(
        name="capacity_status",
        primary_key="asset_id, status_ts",
        fields=_fields(
            ("asset_id", string),
            ("status_ts", timestamp),
            ("declared_availability_mw", double),
            ("outage_status", string),
            ("derating_factor", double),
            ("source_system", string),
        ),
    )
    forecasts = TableDefinition(
        name="meteologica_forecast",
        primary_key="asset_id, forecast_run_ts, type_code, target_timestamp",
        fields=_fields(
            ("asset_id", string),
            ("forecast_run_ts", timestamp),
            ("type_code", string),
            ("target_timestamp", timestamp),
            ("expected_power_kw", double),
            ("wind_speed_m_s", double),
            ("ghi_w_m2", double),
            ("source_system", string),
        ),
    )
    settlement = TableDefinition(
        name="portfolio_settlement",
        primary_key="portfolio_id, market_code, interval_start",
        fields=_fields(
            ("portfolio_id", string),
            ("market_code", string),
            ("interval_start", timestamp),
            ("interval_end", timestamp),
            ("revenue_eur", double),
            ("volume_mwh", double),
            ("imbalance_cost_eur", double),
            ("clearing_price_eur_mwh", double),
            ("loaded_at", timestamp),
            ("source_system", string),
        ),
    )
    balancing = TableDefinition(
        name="balancing_settlement",
        primary_key="portfolio_id, market_code, interval_start",
        fields=_fields(
            ("portfolio_id", string),
            ("market_code", string),
            ("interval_start", timestamp),
            ("interval_end", timestamp),
            ("capacity_revenue_eur", double),
            ("energy_revenue_eur", double),
            ("penalty_eur", double),
            ("loaded_at", timestamp),
            ("source_system", string),
        ),
    )
    prices = TableDefinition(
        name="market_prices",
        primary_key="market_code, interval_start",
        fields=_fields(
            ("market_code", string),
            ("interval_start", timestamp),
            ("interval_end", timestamp),
            ("clearing_price_eur_mwh", double),
            ("loaded_at", timestamp),
            ("source_system", string),
        ),
    )
    return [
        assets, portfolios, membership, markets, orders, telemetry,
        capacity, forecasts, settlement, balancing, prices,
    ]


def ensure_bucket(config: DatabaseConfig) -> None:
    """Create the warehouse bucket when the MinIO image did not create it yet."""
    import boto3
    from botocore.client import Config

    endpoint = config.s3_endpoint
    if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
        endpoint = f"http://{endpoint}"

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=config.s3_access_key,
        aws_secret_access_key=config.s3_secret_key,
        region_name=config.s3_region,
        config=Config(s3={"addressing_style": "path"}),
    )
    existing = {bucket["Name"] for bucket in client.list_buckets().get("Buckets", [])}
    if config.s3_bucket not in existing:
        client.create_bucket(Bucket=config.s3_bucket)
        logger.info("Created bucket %s", config.s3_bucket)


def main():
    """Main entry point"""
    config = DatabaseConfig()
    ensure_bucket(config)
    data_source = PostgreSQLDataSource(config)
    table_defs = create_trading_definitions()

    # Loader
    loader = GenericDataLoader(
        config=config,
        data_source=data_source,
        table_definitions=table_defs
    )

    # Execute
    loader.load_all_tables()


if __name__ == "__main__":
    main()
