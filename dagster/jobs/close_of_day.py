"""
Close-of-day: materialize ``reference_closes`` then ``ticker_cache`` (Massive → Redis).

Runs daily after market close (20:30 NYC, weekdays).

Usage:
    uv run dagster dev -f definitions.py
"""

from dagster import ScheduleDefinition, define_asset_job

from assets.close_of_day import reference_closes, ticker_cache

close_of_day_job = define_asset_job(
    name="close_of_day_job",
    selection=[reference_closes, ticker_cache],
)

close_of_day_schedule = ScheduleDefinition(
    job=close_of_day_job,
    cron_schedule="30 20 * * 1-5",
    execution_timezone="America/New_York",
)
