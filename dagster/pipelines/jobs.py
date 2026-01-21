from dagster import AssetKey, Config, OpExecutionContext, define_asset_job, job, op
from pyspark.sql.functions import input_file_name, regexp_extract

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


all_jobs = [bronze_minute_aggs_job, backfill_sequential_job, backfill_parallel_job]
