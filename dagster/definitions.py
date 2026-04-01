"""
Unified Dagster definitions — all jobs and schedules in one place.

Usage:
    uv run dagster dev -f definitions.py
"""

from dagster import Definitions

from assets import all_assets
from jobs import all_jobs, all_schedules
from resources import get_configured_resources
from sensors import all_sensors

defs = Definitions(
    assets=all_assets,
    jobs=all_jobs,
    schedules=all_schedules,
    sensors=all_sensors,
    resources=get_configured_resources(),
)
