'''
bronze data ingestion
    - read csv from massive s3
    - write table to iceberg
'''

from pathlib import Path
from typing import Callable

from pyspark.sql import SparkSession
from pyspark.sql.functions import input_file_name, lit, regexp_extract

from .write import write_to_iceberg


def ingest_minute_agg_file(
    spark_session: SparkSession,
    file_key: str,
    log: Callable[[str], None],
    table: str,
    overwrite: bool = False,
) -> int:
    '''
    Ingest a single minute agg CSV into bronze.
    '''
    filename = Path(file_key).name
    date_str = filename.replace('.csv.gz', '')

    s3_path = f's3a://flatfiles/{file_key}'
    log(f'reading {file_key} from massive')

    df = (
        spark_session.read
        .option('header', 'true')
        .option('inferSchema', 'true')
        .csv(s3_path)
    )
    row_count = df.count()
    log(f'read {row_count:,} rows')

    df = df.withColumn('date', lit(date_str))
    write_to_iceberg(
        spark_session=spark_session,
        df=df,
        table=table,
        overwrite=overwrite,
    )

    log(f'wrote to {table} partition date={date_str}')
    return row_count


def ingest_minute_agg_batch(
    spark_session: SparkSession,
    s3_paths: list[str],
    log: Callable[[str], None],
    table: str,
    overwrite: bool = False,
) -> None:
    '''
    ingest multiple aggs in parallel
    '''
    df = (
        spark_session.read
        .option('header', 'true')
        .option('inferSchema', 'true')
        .csv(s3_paths)
        .withColumn('date', regexp_extract(input_file_name(), r'(\d{4}-\d{2}-\d{2})\.csv\.gz', 1))
    )

    write_to_iceberg(spark_session, df, table, overwrite=overwrite)
    log(f'written batch of {len(s3_paths)} files to {table}')
