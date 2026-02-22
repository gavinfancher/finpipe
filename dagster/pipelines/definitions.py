'''
Dagster definitions for the finpy lakehouse.
'''

from dagster import Definitions, load_assets_from_modules

from .assets import equity_bronze_minute_aggs, equity_silver_minute_aggs
from .resources import get_configured_resources
from .jobs import all_jobs
from .sensors import all_sensors

defs = Definitions(
    assets=load_assets_from_modules([equity_bronze_minute_aggs, equity_silver_minute_aggs]),
    jobs=all_jobs,
    sensors=all_sensors,
    resources=get_configured_resources(),
)
