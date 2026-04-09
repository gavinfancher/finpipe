"""
PySpark job: staged parquet → Iceberg bronze.

Lists staged parquet files from S3, reads and writes them in batches.
Each batch is a separate Iceberg append. Partitioned by date only —
ticker stays as a column but not a partition key, avoiding thousands
of tiny S3 files per date.

Runs on EMR Serverless — submitted by the Dagster backfill job after
the EC2 spot instance finishes staging files. Dagster always passes
``--cleanup``: staged objects under ``bronze/staged/`` are removed only
after all batches append successfully (so a failed run keeps S3 staging
for re-drive). Omit ``--cleanup`` for manual CLI tests if you want to
keep staged files.

Usage:
    spark-submit staged_to_bronze.py [--cleanup] [--batch-size N]

Each staged file is one trading day (see ``batch/main.py``). Larger N means
fewer Iceberg commits and usually faster wall time, until executor memory
or the write path spikes — raise N gradually (e.g. 50 → 75 → 100) while
watching the Spark UI, not ``driver`` heap.
"""

import sys

import boto3
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

S3_BUCKET = "finpipe-lakehouse"
STAGED_PREFIX = "bronze/staged/"
BRONZE_TABLE = "glue.finpipe_bronze.equities_minute_aggs"
DEFAULT_BATCH_FILES = 50
"""Staged parquet files per Iceberg append (one file ≈ one calendar day)."""


def _parse_job_args(argv: list[str]) -> tuple[bool, int]:
    do_cleanup = "--cleanup" in argv
    batch_size = DEFAULT_BATCH_FILES
    if "--batch-size" in argv:
        i = argv.index("--batch-size")
        if i + 1 >= len(argv):
            raise SystemExit("--batch-size requires a positive integer")
        try:
            batch_size = int(argv[i + 1])
        except ValueError as e:
            raise SystemExit("--batch-size must be an integer") from e
    if batch_size < 1:
        raise SystemExit("--batch-size must be >= 1")
    return do_cleanup, batch_size

BRONZE_PARQUET_SCHEMA = StructType(
    [
        StructField("ticker", StringType(), True),
        StructField("volume", DoubleType(), True),
        StructField("open", DoubleType(), True),
        StructField("close", DoubleType(), True),
        StructField("high", DoubleType(), True),
        StructField("low", DoubleType(), True),
        StructField("window_start", LongType(), True),
        StructField("transactions", LongType(), True),
        StructField("otc", StringType(), True),
        StructField("date", StringType(), True),
    ]
)


def list_staged_files() -> list[str]:
    """Return sorted S3 URIs for all staged parquet files."""
    s3 = boto3.client("s3", region_name="us-east-1")
    paginator = s3.get_paginator("list_objects_v2")
    paths = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=STAGED_PREFIX):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".parquet"):
                paths.append(f"s3://{S3_BUCKET}/{obj['Key']}")
    paths.sort()
    return paths


def cleanup_staged(bucket: str, prefix: str):
    """Delete all objects under the staged prefix."""
    s3 = boto3.client("s3", region_name="us-east-1")
    paginator = s3.get_paginator("list_objects_v2")
    count = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if objects:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
            count += len(objects)
    print(f"deleted {count} staged files from s3://{bucket}/{prefix}")


def main():
    do_cleanup, batch_size = _parse_job_args(sys.argv)

    spark = SparkSession.builder.appName("finpipe-staged-to-bronze").getOrCreate()

    files = list_staged_files()
    print(f"found {len(files)} staged parquet files")

    if not files:
        print("no staged data to process")
        spark.stop()
        return

    table_exists = spark.catalog.tableExists(BRONZE_TABLE)

    for i in range(0, len(files), batch_size):
        batch_files = files[i : i + batch_size]
        batch_num = i // batch_size + 1
        print(f"batch {batch_num}: {len(batch_files)} files")

        df = spark.read.schema(BRONZE_PARQUET_SCHEMA).parquet(*batch_files)

        if not table_exists:
            (
                df.writeTo(BRONZE_TABLE)
                .tableProperty("write.format.default", "parquet")
                .tableProperty("write.parquet.compression-codec", "zstd")
                .tableProperty("write.target-file-size-bytes", "134217728")
                .partitionedBy("date")
                .create()
            )
            table_exists = True
            print(f"  created {BRONZE_TABLE}")
        else:
            df.writeTo(BRONZE_TABLE).append()
            print(f"  appended")

    n_batches = (len(files) + batch_size - 1) // batch_size
    print(f"done — {len(files)} files in {n_batches} batches (batch_size={batch_size})")

    if do_cleanup:
        cleanup_staged(S3_BUCKET, STAGED_PREFIX)

    spark.stop()


if __name__ == "__main__":
    main()
