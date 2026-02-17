"""Bronze ingestion: read CSVs from Massive S3 and write to Iceberg."""

from pathlib import Path
from typing import Callable

from pyspark.sql import SparkSession
from pyspark.sql.functions import input_file_name, lit, regexp_extract

from .write import write_to_iceberg

TABLE = 'iceberg.bronze.minute_aggs'


def ingest_minute_agg_file(
    session: SparkSession,
    file_key: str,
    log: Callable[[str], None],
    overwrite: bool = False,
) -> int:
    """Ingest a single minute agg CSV into bronze."""
    filename = Path(file_key).name
    date_str = filename.replace('.csv.gz', '')

    s3_path = f's3a://flatfiles/{file_key}'
    log(f'Reading from {s3_path}...')

    df = session.read.option('header', 'true').option('inferSchema', 'true').csv(s3_path)
    row_count = df.count()
    log(f'Read {row_count:,} rows')

    df = df.withColumn('date', lit(date_str))
    write_to_iceberg(session, df, TABLE, overwrite=overwrite)

    log(f'Written to bronze.minute_aggs partition date={date_str}')
    return row_count


def ingest_minute_agg_batch(
    session: SparkSession,
    s3_paths: list[str],
    log: Callable[[str], None],
    overwrite: bool = False,
) -> None:
    """Ingest multiple minute agg CSVs at once via Spark (parallel read)."""
    df = (
        session.read
        .option('header', 'true')
        .option('inferSchema', 'true')
        .csv(s3_paths)
        .withColumn('date', regexp_extract(input_file_name(), r'(\d{4}-\d{2}-\d{2})\.csv\.gz', 1))
    )

    write_to_iceberg(session, df, TABLE, overwrite=overwrite)
    log(f'Written batch of {len(s3_paths)} files to bronze.minute_aggs')
