from dagster import AssetKey, Config, OpExecutionContext, define_asset_job, job, op
from pyspark.sql import functions as F
from pyspark.sql.functions import input_file_name, regexp_extract
from pyspark.sql.window import Window

from .resources import MassiveS3Resource, SparkConnectResource
from .assets.bronze import ingest_minute_agg_file


bronze_minute_aggs_job = define_asset_job(
    name='bronze_minute_aggs_job',
    selection=[AssetKey('bronze_minute_aggs')],
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
    objects = massive_s3.list_objects(prefix=config.prefix)
    file_keys = sorted([obj['Key'] for obj in objects])

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
    objects = massive_s3.list_objects(prefix=config.prefix)
    file_keys = sorted([obj['Key'] for obj in objects])

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

        # Extract date from filename pattern: .../2026-01-14.csv.gz
        df = (
            session.read
            .option('header', 'true')
            .option('inferSchema', 'true')
            .csv(s3_paths)
            .withColumn('date', regexp_extract(input_file_name(), r'(\d{4}-\d{2}-\d{2})\.csv\.gz', 1))
        )

        df.createOrReplaceTempView('batch_data')
        table_exists = session.catalog.tableExists('iceberg.bronze.minute_aggs')

        if not table_exists:
            session.sql('''
                CREATE TABLE iceberg.bronze.minute_aggs USING iceberg
                PARTITIONED BY (date)
                TBLPROPERTIES ('write.format.default'='parquet', 'write.parquet.compression-codec'='zstd')
                AS SELECT * FROM batch_data
            ''')
        elif config.overwrite:
            session.sql('INSERT OVERWRITE iceberg.bronze.minute_aggs SELECT * FROM batch_data')
        else:
            session.sql('INSERT INTO iceberg.bronze.minute_aggs SELECT * FROM batch_data')

        context.log.info(f'  ✓ Batch {batch_num} complete')

    context.log.info(f'Done: {len(file_keys)} files in {len(batches)} batch(es)')


@job
def backfill_sequential_job():
    backfill_sequential()


@job
def backfill_parallel_job():
    backfill_parallel()


# Silver job - run on specific ticker + date from Launchpad
class SilverConfig(Config):
    ticker: str = 'AAPL'
    date: str = '2026-01-14'  # YYYY-MM-DD


def rolling_window(partition_cols, order_col, rows_back):
    return Window.partitionBy(*partition_cols).orderBy(order_col).rowsBetween(-rows_back, 0)


@op
def build_silver_for_ticker(
    context: OpExecutionContext,
    config: SilverConfig,
    spark: SparkConnectResource,
) -> None:
    session = spark.get_session()
    ticker = config.ticker.upper()
    date = config.date

    context.log.info(f'Building silver for {ticker} on {date}')

    # Read bronze filtered by ticker and date
    df = (
        session.table('iceberg.bronze.minute_aggs')
        .filter(F.col('ticker') == ticker)
        .filter(F.col('date') == date)
    )

    row_count = df.count()
    if row_count == 0:
        context.log.warning(f'No data found for {ticker} on {date}')
        return

    context.log.info(f'Found {row_count:,} rows')

    # Convert nanosecond timestamp to Eastern Time
    df = df.withColumn(
        'timestamp',
        F.from_utc_timestamp((F.col('window_start') / 1e9).cast('timestamp'), 'America/New_York')
    )

    # Market session enum: premarket, market, postmarket
    time_minutes = F.hour('timestamp') * 60 + F.minute('timestamp')
    df = df.withColumn(
        'session',
        F.when((time_minutes >= 4 * 60) & (time_minutes < 9 * 60 + 30), 'premarket')
        .when((time_minutes >= 9 * 60 + 30) & (time_minutes < 16 * 60), 'market')
        .when((time_minutes >= 16 * 60) & (time_minutes < 20 * 60), 'postmarket')
        .otherwise('closed')
    )

    # 15-minute rolling metrics
    win_15 = rolling_window(['ticker', 'date'], 'timestamp', 14)
    df = (
        df.withColumn('rolling_15m_avg_close', F.avg('close').over(win_15))
        .withColumn('rolling_15m_avg_volume', F.avg('volume').over(win_15))
        .withColumn('rolling_15m_high', F.max('high').over(win_15))
        .withColumn('rolling_15m_low', F.min('low').over(win_15))
        .withColumn('rolling_15m_total_volume', F.sum('volume').over(win_15))
    )

    # Write to silver (create or append)
    table_name = 'iceberg.silver.minute_aggs'

    if not session.catalog.tableExists(table_name):
        context.log.info('Creating silver.minute_aggs table...')
        (
            df.writeTo(table_name)
            .tableProperty('write.format.default', 'parquet')
            .tableProperty('write.parquet.compression-codec', 'zstd')
            .partitionedBy('date')
            .create()
        )
    else:
        context.log.info(f'Appending {ticker} data for {date}...')
        df.writeTo(table_name).append()

    context.log.info(f'✓ Written {row_count:,} rows to silver.minute_aggs')


@job
def silver_ticker_job():
    build_silver_for_ticker()


all_jobs = [bronze_minute_aggs_job, backfill_sequential_job, backfill_parallel_job, silver_ticker_job]
