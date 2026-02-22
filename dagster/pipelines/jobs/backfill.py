from dagster import AssetKey, Config, OpExecutionContext, define_asset_job, job, op

from ..resources import MassiveS3Resource, SparkConnectResource
from ..transforms.ingest_minute_aggs import ingest_minute_agg_batch, ingest_minute_agg_file


daily_elt_job = define_asset_job(
    name='daily_elt_job',
    selection=[AssetKey('equity_bronze_minute_aggs'), AssetKey('equity_silver_minute_aggs')],
)


class BackfillConfig(Config):
    prefix: str = 'us_stocks_sip/minute_aggs_v1/2026/01/'
    batch_size: int = 0  # 0 = all files
    overwrite: bool = False


# Sequential backfill - one file at a time
@op
def backfill_sequential(
    context: OpExecutionContext,
    config: BackfillConfig,
    massive_s3: MassiveS3Resource,
    spark: SparkConnectResource,
) -> None:
    client = massive_s3.get_client()
    response = client.list_objects_v2(Bucket=massive_s3.bucket, Prefix=config.prefix)
    file_keys = sorted([obj['Key'] for obj in response.get('Contents', [])])

    if not file_keys:
        context.log.warning(f'No files found: {config.prefix}')
        return

    context.log.info(f'Processing {len(file_keys)} files sequentially')
    session = spark.get_session()
    total = 0

    for i, key in enumerate(file_keys, 1):
        context.log.info(f'[{i}/{len(file_keys)}] {key}')
        total += ingest_minute_agg_file(
            session=session,
            file_key=key,
            log=lambda msg: context.log.info(f'  {msg}'),
            overwrite=config.overwrite,
        )

    context.log.info(f'Done: {len(file_keys)} files, {total:,} rows')


# Parallel backfill - reads multiple files at once via Spark
@op
def backfill_parallel(
    context: OpExecutionContext,
    config: BackfillConfig,
    massive_s3: MassiveS3Resource,
    spark: SparkConnectResource,
) -> None:
    client = massive_s3.get_client()
    response = client.list_objects_v2(Bucket=massive_s3.bucket, Prefix=config.prefix)
    file_keys = sorted([obj['Key'] for obj in response.get('Contents', [])])

    if not file_keys:
        context.log.warning(f'No files found: {config.prefix}')
        return

    session = spark.get_session()
    batch_size = config.batch_size
    batches = (
        [file_keys[i:i + batch_size] for i in range(0, len(file_keys), batch_size)]
        if batch_size > 0 else [file_keys]
    )

    context.log.info(f'Processing {len(file_keys)} files in {len(batches)} batch(es)')

    for batch_num, keys in enumerate(batches, 1):
        context.log.info(f'[Batch {batch_num}/{len(batches)}] {len(keys)} files')
        s3_paths = [f's3a://flatfiles/{k}' for k in keys]

        ingest_minute_agg_batch(
            session=session,
            s3_paths=s3_paths,
            log=lambda msg: context.log.info(f'  {msg}'),
            overwrite=config.overwrite,
        )

    context.log.info(f'Done: {len(file_keys)} files in {len(batches)} batch(es)')


@job
def backfill_sequential_job():
    backfill_sequential()


@job
def backfill_parallel_job():
    backfill_parallel()
