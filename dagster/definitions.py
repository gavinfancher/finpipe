"""
Unified Dagster definitions — all jobs and schedules in one place.

Usage:
    uv run dagster dev -f definitions.py
"""

from dagster import Definitions

from close_of_day import close_of_day_job, close_of_day_schedule
from dagster_backfill import backfill_job

defs = Definitions(
    jobs=[backfill_job, close_of_day_job],
    schedules=[close_of_day_schedule],
)
