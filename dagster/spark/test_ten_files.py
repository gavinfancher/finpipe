"""
Test: read 10 staged parquet files, append to Iceberg bronze.
Validates that batch writes work with date-only partitioning.
"""

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
TABLE = "glue.finpipe_bronze.equities_minute_aggs"

SCHEMA = StructType(
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


def main():
    spark = SparkSession.builder.appName("test-ten-files").getOrCreate()

    s3 = boto3.client("s3", region_name="us-east-1")
    paginator = s3.get_paginator("list_objects_v2")
    paths = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=STAGED_PREFIX):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".parquet"):
                paths.append(f"s3://{S3_BUCKET}/{obj['Key']}")
    paths.sort()

    batch = paths[:10]
    print(f"reading {len(batch)} files: {batch[0].split('/')[-1]}..{batch[-1].split('/')[-1]}")

    df = spark.read.schema(SCHEMA).parquet(*batch)

    if spark.catalog.tableExists(TABLE):
        df.writeTo(TABLE).append()
        print(f"appended to {TABLE}")
    else:
        (
            df.writeTo(TABLE)
            .tableProperty("write.format.default", "parquet")
            .tableProperty("write.parquet.compression-codec", "zstd")
            .tableProperty("write.target-file-size-bytes", "134217728")
            .partitionedBy("date")
            .create()
        )
        print(f"created {TABLE}")

    count = spark.sql(f"SELECT count(*) as cnt FROM {TABLE}").collect()[0].cnt
    print(f"table now has {count:,} rows")

    spark.stop()


if __name__ == "__main__":
    main()
