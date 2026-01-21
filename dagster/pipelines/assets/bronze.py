'''
Bronze layer asset - ingest minute aggregates from Massive S3 into Iceberg.
'''

from datetime import datetime
from pathlib import Path
from typing import Callable

from dagster import (
    AssetExecutionContext,
    Config,
    MaterializeResult,
    MetadataValue,
    asset,
)
from pyspark.sql import SparkSession
from pyspark.sql.functions import lit

from ..resources import MassiveS3Resource, SparkConnectResource


class MinuteAggsConfig(Config):
    '''Configuration for minute aggregates ingestion.'''

    file_key: str = ''  # e.g., us_stocks_sip/minute_aggs_v1/2026/01/2026-01-14.csv.gz
    overwrite: bool = False  # False = append, True = overwrite partition


def ingest_minute_agg_file(
    session: SparkSession,
    file_key: str,
    log: Callable[[str], None],
    overwrite: bool = False,
) -> int:
    '''
    Ingest a single minute aggregate file into Iceberg.

    Shared logic used by both the bronze asset and backfill job.

    Args:
        session: Active SparkSession (caller manages lifecycle)
        file_key: S3 key of the file to ingest
        log: Logging function
        overwrite: If True, overwrite partition; if False, append (default)

    Returns:
        Number of rows ingested
    '''
    # Extract date from filename
    # Format: us_stocks_sip/minute_aggs_v1/2026/01/2026-01-14.csv.gz
    filename = Path(file_key).name  # 2026-01-14.csv.gz
    date_str = filename.replace('.csv.gz', '')  # 2026-01-14

    # Read from Massive S3
    s3_path = f's3a://flatfiles/{file_key}'
    log(f'Reading from {s3_path}...')

    df = (
        session.read
        .option('header', 'true')
        .option('inferSchema', 'true')
        .csv(s3_path)
    )

    row_count = df.count()
    log(f'Read {row_count:,} rows')

    # Add date partition column
    df = df.withColumn('date', lit(date_str))

    # Write to Iceberg bronze table
    table_exists = session.catalog.tableExists('iceberg.bronze.minute_aggs')

    if not table_exists:
        log('Creating bronze.minute_aggs table...')
        (
            df.writeTo('iceberg.bronze.minute_aggs')
            .tableProperty('write.format.default', 'parquet')
            .tableProperty('write.parquet.compression-codec', 'zstd')
            .partitionedBy('date')
            .create()
        )
    elif overwrite:
        log(f'Overwriting partition date={date_str}...')
        (
            df.writeTo('iceberg.bronze.minute_aggs')
            .overwritePartitions()
        )
    else:
        log(f'Appending to partition date={date_str}...')
        (
            df.writeTo('iceberg.bronze.minute_aggs')
            .append()
        )

    log(f'Written to bronze.minute_aggs partition date={date_str}')
    return row_count


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

    session = spark.get_session()

    row_count = ingest_minute_agg_file(
        session=session,
        file_key=file_key,
        log=context.log.info,
        overwrite=config.overwrite,
    )

    # Extract date for metadata
    filename = Path(file_key).name
    date_str = filename.replace('.csv.gz', '')

    return MaterializeResult(
        metadata={
            'row_count': MetadataValue.int(int(row_count)),
            'date': MetadataValue.text(date_str),
            'source_file': MetadataValue.text(file_key),
            'table': MetadataValue.text('iceberg.bronze.minute_aggs'),
        }
    )
    # Note: Don't call session.stop() - Spark Connect clients don't own the server
