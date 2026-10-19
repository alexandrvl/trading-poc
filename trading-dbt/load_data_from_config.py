"""
Example: Load data using configuration file

This script demonstrates how to use the generic loader framework
with a JSON configuration file instead of hardcoded table definitions.
"""

import json
import logging
from load_data_generic import (
    DatabaseConfig,
    PostgreSQLDataSource,
    GenericDataLoader,
    ConfigLoader
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Load tables defined in configuration file"""

    # 1. Load configuration
    logger.info("Loading table configuration from file...")
    with open('table_config.example.json', 'r') as f:
        config_dict = json.load(f)

    # 2. Convert to table definitions
    table_defs = ConfigLoader.from_dict(config_dict)
    logger.info(f"Loaded {len(table_defs)} table definitions")

    # 3. Setup database and source
    config = DatabaseConfig()
    data_source = PostgreSQLDataSource(config)

    # 4. Create loader and execute
    loader = GenericDataLoader(
        config=config,
        data_source=data_source,
        table_definitions=table_defs
    )

    logger.info("Starting data load process...")
    loader.load_all_tables()
    logger.info("Data load complete!")


if __name__ == "__main__":
    main()
