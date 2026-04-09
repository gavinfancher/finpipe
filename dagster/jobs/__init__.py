"""Job and schedule definitions for finpipe-dagster."""

from jobs.backfill import backfill_job, commit_staged_to_bronze_job
from jobs.close_of_day import close_of_day_job, close_of_day_schedule
from jobs.daily_lakehouse import daily_lakehouse_job

all_jobs = [
    backfill_job,
    commit_staged_to_bronze_job,
    close_of_day_job,
    daily_lakehouse_job,
]
all_schedules = [close_of_day_schedule]
