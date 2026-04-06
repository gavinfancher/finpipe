"""Sensor definitions for finpipe-dagster."""

from .daily_ingest import daily_ingest_sensor

all_sensors = [daily_ingest_sensor]
