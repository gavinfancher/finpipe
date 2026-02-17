from datetime import datetime

from dagster import (
    DefaultSensorStatus,
    RunConfig,
    RunRequest,
    SensorEvaluationContext,
    SensorResult,
    SkipReason,
    sensor
)

from ..resources import MassiveS3Resource
from ..jobs import bronze_minute_aggs_job
from ..assets.bronze_minute_aggs import MinuteAggsConfig


# Monitors Massive S3 for new minute aggregate files
@sensor(
    name='massive_minute_aggs_sensor',
    minimum_interval_seconds=60,
    default_status=DefaultSensorStatus.RUNNING,
    job=bronze_minute_aggs_job,
)
def massive_minute_aggs_sensor(
    context: SensorEvaluationContext,
    massive_s3: MassiveS3Resource,
) -> SensorResult | SkipReason:
    now = datetime.now()

    try:
        prefix = f'us_stocks_sip/minute_aggs_v1/{now.year}/{now.month:02d}/'
        client = massive_s3.get_client()
        response = client.list_objects_v2(Bucket=massive_s3.bucket, Prefix=prefix)
        objects = response.get('Contents', [])
    except Exception as e:
        context.log.error(f'Failed to list Massive S3: {e}')
        return SkipReason(f'Massive S3 connection failed: {e}')

    if not objects:
        return SkipReason(f'No files found for {now.year}/{now.month:02d}')

    last_processed = context.cursor or ''
    all_keys = sorted([obj['Key'] for obj in objects])
    new_files = [k for k in all_keys if k > last_processed]

    if not new_files:
        return SkipReason('No new files since last check')

    next_file = new_files[0]
    context.log.info(f'New file: {next_file}')

    return SensorResult(
        run_requests=[
            RunRequest(
                run_key=f'minute-aggs-{next_file}',
                run_config=RunConfig(
                    ops={'bronze_minute_aggs': MinuteAggsConfig(file_key=next_file)}
                ),
                tags={'sensor': 'massive_minute_aggs_sensor', 'file': next_file},
            )
        ],
        cursor=next_file,
    )


all_sensors = [massive_minute_aggs_sensor]
