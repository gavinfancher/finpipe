'''
Sensor to monitor Massive S3 for new minute aggregate files.
'''

from datetime import datetime

from dagster import (
    AssetKey,
    DefaultSensorStatus,
    RunConfig,
    RunRequest,
    SensorEvaluationContext,
    SensorResult,
    SkipReason,
    define_asset_job,
    sensor,
)

from .resources import MassiveS3Resource
from .assets.bronze import MinuteAggsConfig


# Define the job that materializes the bronze asset
bronze_minute_aggs_job = define_asset_job(
    name='bronze_minute_aggs_job',
    selection=[AssetKey('bronze_minute_aggs')],
    description='Job to ingest minute aggregates from Massive S3 into bronze layer.',
)


@sensor(
    name='massive_minute_aggs_sensor',
    description='Monitors Massive S3 for new minute aggregate files to ingest.',
    minimum_interval_seconds=3600,  # Check hourly (files updated at 11am ET)
    default_status=DefaultSensorStatus.RUNNING,
    job=bronze_minute_aggs_job,
)
def massive_minute_aggs_sensor(
    context: SensorEvaluationContext,
    massive_s3: MassiveS3Resource,
) -> SensorResult | SkipReason:
    '''
    Sensor that monitors Massive S3 for new minute aggregate files.

    Files are located at: us_stocks_sip/minute_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz
    Updated daily at 11am ET with previous day's data.
    '''
    now = datetime.now()
    year = now.year
    month = now.month

    try:
        objects = massive_s3.list_minute_aggs(year=year, month=month)
    except Exception as e:
        context.log.error(f'Failed to list Massive S3 objects: {e}')
        return SkipReason(f'Massive S3 connection failed: {e}')

    if not objects:
        return SkipReason(f'No minute agg files found for {year}/{month:02d}')

    # Parse cursor for last processed file
    last_processed_key = context.cursor or ''

    # Find new files (sorted by key = date order)
    all_keys = sorted([obj['Key'] for obj in objects])
    new_files = [k for k in all_keys if k > last_processed_key]

    if not new_files:
        return SkipReason('No new minute aggregate files since last check')

    # Process one file at a time to avoid overwhelming the system
    next_file = new_files[0]
    context.log.info(f'Found new minute agg file: {next_file}')

    return SensorResult(
        run_requests=[
            RunRequest(
                run_key=f'minute-aggs-{next_file}',
                run_config=RunConfig(
                    ops={'bronze_minute_aggs': MinuteAggsConfig(file_key=next_file)}
                ),
                tags={
                    'sensor': 'massive_minute_aggs_sensor',
                    'file': next_file,
                },
            )
        ],
        cursor=next_file,
    )


# Export sensors and jobs
all_sensors = [massive_minute_aggs_sensor]
all_jobs = [bronze_minute_aggs_job]
