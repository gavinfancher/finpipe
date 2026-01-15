"""
Dagster definitions for the finpy lakehouse.

Configures resources, assets, and sensors for the data pipeline.
"""

from pathlib import Path

from dotenv import load_dotenv
from dagster import Definitions, load_assets_from_modules

# Load .env from the dagster/ directory (parent of pipelines/)
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

from .assets import bronze
from .resources import get_configured_resources
from .sensors import all_sensors, all_jobs

# Load all assets
all_assets = load_assets_from_modules([bronze])

# Get configured resources from environment
resources = get_configured_resources()

defs = Definitions(
    assets=all_assets,
    jobs=all_jobs,
    sensors=all_sensors,
    resources=resources,
)
