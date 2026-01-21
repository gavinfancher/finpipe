'''
Sensors and jobs for minute aggregate ingestion.
'''

from datetime import datetime

from dagster import (
    AssetKey,
    Config,
    DefaultSensorStatus,
    OpExecutionContext,
    RunConfig,
    RunRequest,
    SensorEvaluationContext,
    SensorResult,
    SkipReason,
    define_asset_job,
    job,
    op,
    sensor,
)

from .resources import MassiveS3Resource, SparkConnectResource
from .assets.bronze import MinuteAggsConfig, ingest_minute_agg_file


# Define the job that materializes the bronze asset
bronze_minute_aggs_job = define_asset_job(
    name='bronze_minute_aggs_job',
    selection=[AssetKey('bronze_minute_aggs')],
    description='Job to ingest minute aggregates from Massive S3 into bronze layer.',
)


@sensor(
    name='massive_minute_aggs_sensor',
    description='Monitors Massive S3 for new minute aggregate files to ingest.',
    minimum_interval_seconds=60,  # Check hourly (files updated at 11am ET)
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


# =============================================================================
# Backfill Job - Manual run through Dagster UI (sequential, one file at a time)
# =============================================================================


class BackfillConfig(Config):
    '''Configuration for backfill job.'''

    prefix: str = 'us_stocks_sip/minute_aggs_v1/2026/01/'  # Default: January 2026
    batch_size: int = 0  # For batch job: 0 = all files, >0 = files per batch
    overwrite: bool = False  # False = append, True = overwrite partitions


@op
def backfill_minute_aggs(
    context: OpExecutionContext,
    config: BackfillConfig,
    massive_s3: MassiveS3Resource,
    spark: SparkConnectResource,
) -> None:
    '''
    Backfill all minute aggregate files under the given prefix (sequential).

    Configure the prefix in the Launchpad, e.g.:
        us_stocks_sip/minute_aggs_v1/2026/01/   # January 2026
        us_stocks_sip/minute_aggs_v1/2026/02/   # February 2026

    Uses the same Spark ingestion logic as the bronze_minute_aggs asset.
    '''
    prefix = config.prefix
    context.log.info(f'Backfilling with prefix: {prefix}')

    # List all files under the prefix
    objects = massive_s3.list_objects(prefix=prefix)
    file_keys = sorted([obj['Key'] for obj in objects])

    if not file_keys:
        context.log.warning(f'No files found with prefix: {prefix}')
        return

    context.log.info(f'Found {len(file_keys)} files to process')

    session = spark.get_session()

    total_rows = 0
    for i, file_key in enumerate(file_keys, 1):
        context.log.info(f'[{i}/{len(file_keys)}] {file_key}')

        # Use shared ingestion logic from bronze asset
        row_count = ingest_minute_agg_file(
            session=session,
            file_key=file_key,
            log=lambda msg: context.log.info(f'  {msg}'),
            overwrite=config.overwrite,
        )
        total_rows += row_count

    context.log.info(
        f'Backfill complete! Processed {len(file_keys)} files, '
        f'{total_rows:,} total rows.'
    )
    # Note: Don't call session.stop() - Spark Connect clients don't own the server


@job(
    description='Backfill minute aggregates sequentially (one file at a time). '
                'Configure the prefix in the Launchpad.',
)
def backfill_minute_aggs_job():
    '''Backfill job - run from Dagster UI Launchpad.'''
    backfill_minute_aggs()


# =============================================================================
# Batch Backfill Job - Parallel read of multiple files at once
# =============================================================================


@op
def batch_backfill_minute_aggs(
    context: OpExecutionContext,
    config: BackfillConfig,
    massive_s3: MassiveS3Resource,
    spark: SparkConnectResource,
) -> None:
    '''
    Batch backfill - reads files under prefix in parallel batches.

    This gives better performance by:
    - Reading multiple files at once (1 partition per file = parallel reads)
    - Extracting date from filename using Spark
    - Writing partitions in batches

    Configure in Launchpad:
        prefix: us_stocks_sip/minute_aggs_v1/2026/01/
        batch_size: 0 (all at once) or 5-10 (files per batch)
    '''
    from pyspark.sql.functions import input_file_name, regexp_extract

    prefix = config.prefix
    batch_size = config.batch_size
    context.log.info(f'Batch backfilling with prefix: {prefix}')

    # List all files under the prefix
    objects = massive_s3.list_objects(prefix=prefix)
    file_keys = sorted([obj['Key'] for obj in objects])

    if not file_keys:
        context.log.warning(f'No files found with prefix: {prefix}')
        return

    context.log.info(f'Found {len(file_keys)} files total')

    session = spark.get_session()

    # Split into batches if batch_size > 0
    if batch_size > 0:
        batches = [file_keys[i:i + batch_size] for i in range(0, len(file_keys), batch_size)]
        context.log.info(f'Processing in {len(batches)} batches of up to {batch_size} files')
    else:
        batches = [file_keys]
        context.log.info('Processing all files in one batch')

    for batch_num, batch_keys in enumerate(batches, 1):
        context.log.info(f'[Batch {batch_num}/{len(batches)}] Processing {len(batch_keys)} files...')

        # Build S3 paths for this batch
        s3_paths = [f's3a://flatfiles/{key}' for key in batch_keys]

        # Read files in parallel
        df = (
            session.read
            .option('header', 'true')
            .option('inferSchema', 'true')
            .csv(s3_paths)
        )

        # Extract date from the input filename
        # Filename format: .../2026-01-14.csv.gz
        df = df.withColumn(
            'date',
            regexp_extract(input_file_name(), r'(\d{4}-\d{2}-\d{2})\.csv\.gz', 1)
        )

        # Write to Iceberg using SQL (more stable with Spark Connect)
        table_exists = session.catalog.tableExists('iceberg.bronze.minute_aggs')

        # Register temp view for SQL access
        df.createOrReplaceTempView('batch_data')

        if not table_exists:
            context.log.info('  Creating bronze.minute_aggs table...')
            session.sql('''
                CREATE TABLE iceberg.bronze.minute_aggs
                USING iceberg
                PARTITIONED BY (date)
                TBLPROPERTIES (
                    'write.format.default' = 'parquet',
                    'write.parquet.compression-codec' = 'zstd'
                )
                AS SELECT * FROM batch_data
            ''')
        elif config.overwrite:
            context.log.info('  Overwriting partitions...')
            session.sql('''
                INSERT OVERWRITE iceberg.bronze.minute_aggs
                SELECT * FROM batch_data
            ''')
        else:
            context.log.info('  Appending data...')
            session.sql('''
                INSERT INTO iceberg.bronze.minute_aggs
                SELECT * FROM batch_data
            ''')

        context.log.info(f'  ✓ Batch {batch_num} complete')

    context.log.info(f'Batch backfill complete! Processed {len(file_keys)} files.')


@job(
    description='Batch backfill - reads ALL files in parallel for better performance. '
                'Configure the prefix in the Launchpad.',
)
def batch_backfill_job():
    '''Batch backfill job - parallel file reads.'''
    batch_backfill_minute_aggs()


# Export sensors and jobs
all_sensors = [massive_minute_aggs_sensor]
all_jobs = [bronze_minute_aggs_job, backfill_minute_aggs_job, batch_backfill_job]
