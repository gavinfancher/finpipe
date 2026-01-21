'''
Bronze layer asset - ingest minute aggregates from Massive S3 into Iceberg.
'''

from datetime import datetime
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    Config,
    MaterializeResult,
    MetadataValue,
    asset,
)

from ..resources import MassiveS3Resource, SparkConnectResource


class MinuteAggsConfig(Config):
    '''Configuration for minute aggregates ingestion.'''

    file_key: str = ''  # e.g., us_stocks_sip/minute_aggs_v1/2026/01/2026-01-14.csv.gz


@asset(
    name='bronze_minute_aggs',
    group_name='bronze',
    description='Minute aggregate data from Massive S3 ingested into bronze Iceberg table.',
    compute_kind='spark',
)
def bronze_minute_aggs(
    context: AssetExecutionContext,
    config: MinuteAggsConfig,
    massive_s3: MassiveS3Resource,
    spark: SparkConnectResource,
) -> MaterializeResult:
    '''
    Ingest minute aggregate data from Massive S3 into bronze layer.

    Spark reads directly from Massive S3 (flatfiles bucket) and writes to Iceberg.
    No staging step needed - Spark has Massive credentials configured.
    '''
    # Determine which file to process
    file_key = config.file_key
    if not file_key:
        # If no specific file, get the latest
        now = datetime.now()
        objects = massive_s3.list_minute_aggs(year=now.year, month=now.month)
        if not objects:
            context.log.warning('No minute agg files found')
            return MaterializeResult(
                metadata={'status': MetadataValue.text('no_files')}
            )
        file_key = sorted([o['Key'] for o in objects])[-1]

    context.log.info(f'Processing file: {file_key}')

    # Extract date from filename for partitioning
    # Format: us_stocks_sip/minute_aggs_v1/2026/01/2026-01-14.csv.gz
    filename = Path(file_key).name  # 2026-01-14.csv.gz
    date_str = filename.replace('.csv.gz', '')  # 2026-01-14

    # Spark reads directly from Massive S3 (flatfiles bucket)
    # Spark has per-bucket credentials configured for s3a://flatfiles/
    s3_path = f's3a://flatfiles/{file_key}'

    session = spark.get_session()

    try:
        context.log.info(f'Spark reading directly from {s3_path}...')
        df = (
            session.read
            .option('header', 'true')
            .option('inferSchema', 'true')
            .csv(s3_path)
        )

        row_count = df.count()
        context.log.info(f'Read {row_count} rows')

        # Add date partition column
        from pyspark.sql.functions import lit
        df = df.withColumn('date', lit(date_str))

        # Write to Iceberg bronze table
        # Note: bronze namespace must exist - create via:
        # docker exec spark-iceberg spark-sql -e "CREATE NAMESPACE IF NOT EXISTS iceberg.bronze"
        context.log.info('Writing to bronze.minute_aggs...')
        (
            df.writeTo('iceberg.bronze.minute_aggs')
            .tableProperty('write.format.default', 'parquet')
            .tableProperty('write.parquet.compression-codec', 'zstd')
            .partitionedBy('date')
            .createOrReplace()
        )

        context.log.info('Successfully wrote to bronze.minute_aggs')

        return MaterializeResult(
            metadata={
                'row_count': MetadataValue.int(int(row_count)),
                'date': MetadataValue.text(date_str),
                'source_file': MetadataValue.text(file_key),
                'table': MetadataValue.text('iceberg.bronze.minute_aggs'),
            }
        )

    finally:
        session.stop()
