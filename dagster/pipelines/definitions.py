'''
Dagster definitions for the finpy lakehouse.
'''

from pathlib import Path

from dotenv import load_dotenv
from dagster import Definitions, load_assets_from_modules

# Load .env from dagster/ directory
load_dotenv(Path(__file__).parent.parent / '.env')

from .assets import bronze
from .resources import get_configured_resources
from .jobs import all_jobs
from .sensors import all_sensors

defs = Definitions(
    assets=load_assets_from_modules([bronze]),
    jobs=all_jobs,
    sensors=all_sensors,
    resources=get_configured_resources(),
)
