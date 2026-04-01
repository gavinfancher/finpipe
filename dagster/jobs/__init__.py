"""Job and schedule definitions for finpipe-dagster."""

from jobs.backfill import backfill_job
from jobs.close_of_day import close_of_day_job, close_of_day_schedule

all_jobs = [backfill_job, close_of_day_job]
all_schedules = [close_of_day_schedule]
