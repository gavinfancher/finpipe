"""
PySpark job: staged parquet → Iceberg bronze.

Reads all staged parquet files written by the backfill batch job,
writes to Iceberg bronze table, then cleans up staged files on success.

Runs on EMR Serverless — submitted by the Dagster backfill job after
the EC2 spot instance finishes staging files.

Usage:
    spark-submit staged_to_bronze.py [--cleanup]
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
STAGED_PATH = f"s3://{S3_BUCKET}/bronze/staged/"
BRONZE_TABLE = "glue.finpipe_bronze.equities_minute_aggs"

# Align with common.schemas.BRONZE_SCHEMA (PyArrow batch writer).
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
    do_cleanup = "--cleanup" in sys.argv

    spark = SparkSession.builder.appName("finpipe-staged-to-bronze").getOrCreate()

    # Nested keys: bronze/staged/{year}/*.parquet — recurse and ignore non-parquet S3 keys.
    df = (
        spark.read.option("recursiveFileLookup", "true")
        .option("pathGlobFilter", "*.parquet")
        .schema(BRONZE_PARQUET_SCHEMA)
        .parquet(STAGED_PATH)
    )
    row_count = df.count()
    print(f"read {row_count:,} rows from {STAGED_PATH}")

    if row_count == 0:
        print("no staged data to process")
        spark.stop()
        return

    # Shuffle width ~ executor parallelism (see backfill EMR spark.sql.shuffle.partitions).
    spark.conf.set("spark.sql.shuffle.partitions", "96")
    df = df.repartition(96, "date", "ticker")

    # Fanout writer: avoid global sort-by-partition shuffle on create (major source of OOM vs raw size).
    # https://iceberg.apache.org/docs/latest/spark-writes/
    w = df.writeTo(BRONZE_TABLE).option("fanout-enabled", "true")

    # write to iceberg
    if spark.catalog.tableExists(BRONZE_TABLE):
        w.append()
        print(f"appended to {BRONZE_TABLE}")
    else:
        w.partitionedBy("date", "ticker").create()
        print(f"created {BRONZE_TABLE}")

    print(f"wrote {row_count:,} rows to {BRONZE_TABLE}")

    if do_cleanup:
        cleanup_staged(S3_BUCKET, "bronze/staged/")

    spark.stop()


if __name__ == "__main__":
    main()
