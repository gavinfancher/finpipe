"""
Sensor: detect new minute agg files on Massive S3.

Polls every 5 minutes, triggers bronze_minute_aggs materialization
for each new file. Uses a cursor to track the last processed file key.
"""

import pendulum
from dagster import (
    DefaultSensorStatus,
    RunConfig,
    RunRequest,
    SensorEvaluationContext,
    SensorResult,
    SkipReason,
    sensor,
)

from assets.bronze_minute_aggs import BronzeIngestConfig
from resources.massive_s3 import MassiveS3Resource

PREFIX = "us_stocks_sip/minute_aggs_v1"


def _prefixes_to_check(now: pendulum.DateTime) -> list[str]:
    """Current month, plus previous month if within 24h of month boundary."""
    prefixes = [f"{PREFIX}/{now.year}/{now.month:02d}/"]
    first_of_month = now.start_of("month")
    if now.diff(first_of_month).in_hours() < 24:
        prev = first_of_month.subtract(days=1)
        prefixes.append(f"{PREFIX}/{prev.year}/{prev.month:02d}/")
    return prefixes


@sensor(
    name="daily_ingest_sensor",
    minimum_interval_seconds=300,
    default_status=DefaultSensorStatus.STOPPED,
    target=["bronze_minute_aggs"],
)
def daily_ingest_sensor(
    context: SensorEvaluationContext,
    massive_s3: MassiveS3Resource,
) -> SensorResult | SkipReason:
    """Poll Massive S3 for new minute agg files."""
    now = pendulum.now("America/New_York")
    last_processed = context.cursor or ""

    try:
        all_keys = []
        for prefix in _prefixes_to_check(now):
            all_keys.extend(massive_s3.list_keys(prefix))
    except Exception as e:
        context.log.error("failed to list Massive S3: %s", e)
        return SkipReason(f"S3 connection failed: {e}")

    new_files = sorted(k for k in all_keys if k > last_processed)

    if not new_files:
        return SkipReason("no new files")

    # process one file at a time so each gets its own dagster run
    next_file = new_files[0]
    context.log.info("new file: %s (%d pending)", next_file, len(new_files))

    return SensorResult(
        run_requests=[
            RunRequest(
                run_key=f"bronze-{next_file}",
                run_config=RunConfig(
                    ops={"bronze_minute_aggs": BronzeIngestConfig(file_key=next_file)},
                ),
                tags={"file": next_file},
            ),
        ],
        cursor=next_file,
    )
