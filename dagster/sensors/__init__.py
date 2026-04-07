"""Sensor definitions for finpipe-dagster."""

from .daily_ingest import daily_ingest_sensor
from jobs.backfill import backfill_cleanup_sensor

all_sensors = [daily_ingest_sensor, backfill_cleanup_sensor]
