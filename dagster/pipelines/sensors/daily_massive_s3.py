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

from ..resources import MassiveS3Resource
from ..jobs import daily_elt_job
from ..assets.bronze_minute_aggs import MinuteAggsConfig

PREFIX = 'us_stocks_sip/minute_aggs_v1'


def _list_keys(client, bucket: str, prefix: str) -> list[str]:
    keys = []
    response = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    keys.extend(obj['Key'] for obj in response.get('Contents', []))
    while response.get('IsTruncated'):
        response = client.list_objects_v2(
            Bucket=bucket, Prefix=prefix,
            ContinuationToken=response['NextContinuationToken'],
        )
        keys.extend(obj['Key'] for obj in response.get('Contents', []))
    return sorted(keys)


def _prefixes_to_check(now: pendulum.DateTime) -> list[str]:
    """Current month always. Previous month if within 24h of month boundary."""
    prefixes = [f'{PREFIX}/{now.year}/{now.month:02d}/']
    first_of_month = now.start_of('month')
    if now.diff(first_of_month).in_hours() < 24:
        prev = first_of_month.subtract(days=1)
        prefixes.append(f'{PREFIX}/{prev.year}/{prev.month:02d}/')
    return prefixes


@sensor(
    name='daily_massive_s3_sensor',
    minimum_interval_seconds=300,
    default_status=DefaultSensorStatus.RUNNING,
    job=daily_elt_job,
)
def daily_massive_s3_sensor(
    context: SensorEvaluationContext,
    massive_s3: MassiveS3Resource,
) -> SensorResult | SkipReason:
    now = pendulum.now()
    last_processed = context.cursor or ''

    try:
        client = massive_s3.get_client()
        all_keys = []
        for prefix in _prefixes_to_check(now):
            all_keys.extend(_list_keys(client, massive_s3.bucket, prefix))
    except Exception as e:
        context.log.error(f'Failed to list Massive S3: {e}')
        return SkipReason(f'S3 connection failed: {e}')

    new_files = sorted(k for k in all_keys if k > last_processed)

    if not new_files:
        return SkipReason('No new files')

    # process one file at a time so each gets its own dagster run
    next_file = new_files[0]
    context.log.info(f'New file: {next_file} ({len(new_files)} pending)')

    return SensorResult(
        run_requests=[
            RunRequest(
                run_key=f'minute-aggs-{next_file}',
                run_config=RunConfig(
                    ops={'bronze_minute_aggs': MinuteAggsConfig(file_key=next_file)}
                ),
                tags={'file': next_file},
            )
        ],
        cursor=next_file,
    )
