"""
Bronze layer asset - ingest minute aggregates from Massive S3 into Iceberg.
"""

from datetime import datetime
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    Config,
    MaterializeResult,
    MetadataValue,
    asset,
)

from ..resources import MassiveS3Resource, MinioResource, SparkConnectResource


class MinuteAggsConfig(Config):
    """Configuration for minute aggregates ingestion."""

    file_key: str = ""  # e.g., us_stocks_sip/minute_aggs_v1/2026/01/2026-01-14.csv.gz


@asset(
    name="bronze_minute_aggs",
    group_name="bronze",
    description="Minute aggregate data from Massive S3 ingested into bronze Iceberg table.",
    compute_kind="spark",
)
def bronze_minute_aggs(
    context: AssetExecutionContext,
    config: MinuteAggsConfig,
    massive_s3: MassiveS3Resource,
    minio: MinioResource,
    spark: SparkConnectResource,
) -> MaterializeResult:
    """
    Ingest minute aggregate data from Massive S3 into bronze layer.

    Flow:
    1. Dagster downloads gzipped CSV from Massive S3 (boto3 works, Hadoop S3A doesn't)
    2. Uploads to MinIO staging area (so remote Spark can access it)
    3. Spark reads from MinIO and writes to bronze.minute_aggs Iceberg table

    Note: Direct Spark->Massive S3 access doesn't work due to Hadoop S3A
    incompatibility with Massive's S3 API. This staging approach adds ~20s
    but is reliable. To optimize, run Dagster on the same VM as the lakehouse.
    """
    # Determine which file to process
    file_key = config.file_key
    if not file_key:
        # If no specific file, get the latest
        now = datetime.now()
        objects = massive_s3.list_minute_aggs(year=now.year, month=now.month)
        if not objects:
            context.log.warning("No minute agg files found")
            return MaterializeResult(
                metadata={"status": MetadataValue.text("no_files")}
            )
        file_key = sorted([o["Key"] for o in objects])[-1]

    context.log.info(f"Processing file: {file_key}")

    # Extract date from filename for partitioning
    # Format: us_stocks_sip/minute_aggs_v1/2026/01/2026-01-14.csv.gz
    filename = Path(file_key).name  # 2026-01-14.csv.gz
    date_str = filename.replace(".csv.gz", "")  # 2026-01-14

    # Download from Massive S3 (boto3 works reliably)
    context.log.info(f"Downloading {file_key} from Massive S3...")
    file_data = massive_s3.get_object(file_key)
    context.log.info(f"Downloaded {len(file_data)} bytes")

    # Upload to MinIO staging area (so remote Spark can access it)
    staging_key = f"staging/minute_aggs/{filename}"
    context.log.info(f"Uploading to MinIO: s3://warehouse/{staging_key}")
    minio.upload_file(bucket="warehouse", key=staging_key, data=file_data)

    # Now Spark can read from MinIO
    s3_path = f"s3a://warehouse/{staging_key}"

    session = spark.get_session()

    try:
        # Spark reads gzipped CSV directly from MinIO
        # Note: bronze namespace must exist - create via:
        # docker exec spark-iceberg spark-sql -e "CREATE NAMESPACE IF NOT EXISTS iceberg.bronze"
        context.log.info(f"Reading {s3_path} with Spark...")
        df = (
            session.read
            .option("header", "true")
            .option("inferSchema", "true")
            .csv(s3_path)
        )

        row_count = df.count()
        context.log.info(f"Read {row_count} rows")

        # Add date partition column
        from pyspark.sql.functions import lit
        df = df.withColumn("date", lit(date_str))

        # Write to Iceberg bronze table
        context.log.info("Writing to bronze.minute_aggs...")
        (
            df.writeTo("iceberg.bronze.minute_aggs")
            .tableProperty("write.format.default", "parquet")
            .tableProperty("write.parquet.compression-codec", "zstd")
            .partitionedBy("date")
            .createOrReplace()
        )

        context.log.info("Successfully wrote to bronze.minute_aggs")

        return MaterializeResult(
            metadata={
                "row_count": MetadataValue.int(row_count),
                "date": MetadataValue.text(date_str),
                "source_file": MetadataValue.text(file_key),
                "staging_path": MetadataValue.text(s3_path),
                "table": MetadataValue.text("iceberg.bronze.minute_aggs"),
            }
        )

    finally:
        session.stop()
