"""
Test: read one staged parquet file, write to Iceberg bronze.

Run directly via EMR Serverless to validate the write path
without Dagster in the loop.

Usage (from repo root):
    # upload
    aws s3 cp dagster/spark/test_one_file.py s3://finpipe-lakehouse/scripts/test_one_file.py

    # submit
    aws emr-serverless start-job-run \
        --application-id <APP_ID> \
        --execution-role-arn <ROLE_ARN> \
        --name test-one-file \
        --job-driver '{
            "sparkSubmit": {
                "entryPoint": "s3://finpipe-lakehouse/scripts/test_one_file.py",
                "sparkSubmitParameters": "--conf spark.jars=/usr/share/aws/iceberg/lib/iceberg-spark3-runtime.jar --conf spark.sql.catalog.glue=org.apache.iceberg.spark.SparkCatalog --conf spark.sql.catalog.glue.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog --conf spark.sql.catalog.glue.warehouse=s3://finpipe-lakehouse/iceberg/ --conf spark.sql.catalog.glue.io-impl=org.apache.iceberg.aws.s3.S3FileIO --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions --conf spark.sql.defaultCatalog=glue --conf spark.executor.memory=6g --conf spark.driver.memory=6g --conf spark.executor.cores=1 --conf spark.dynamicAllocation.enabled=false --conf spark.executor.instances=2"
            }
        }' \
        --tags '{"project":"finpipe"}'
"""

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

S3_BUCKET = "finpipe-lakehouse"
TEST_FILE = f"s3://{S3_BUCKET}/bronze/staged/2025/2025-01-02.parquet"
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
    spark = SparkSession.builder.appName("test-one-file").getOrCreate()

    df = spark.read.schema(SCHEMA).parquet(TEST_FILE)
    count = df.count()
    print(f"read {count:,} rows from {TEST_FILE}")

    dates = [r.date for r in df.select("date").distinct().collect()]
    tickers = df.select("ticker").distinct().count()
    print(f"dates: {dates}, distinct tickers: {tickers}")

    if spark.catalog.tableExists(TABLE):
        print(f"table {TABLE} exists — dropping first for clean test")
        spark.sql(f"DROP TABLE {TABLE}")

    (
        df.writeTo(TABLE)
        .tableProperty("write.format.default", "parquet")
        .tableProperty("write.parquet.compression-codec", "zstd")
        .tableProperty("write.target-file-size-bytes", "134217728")
        .partitionedBy("date")
        .create()
    )
    print(f"created {TABLE} with {count:,} rows")

    verify = spark.sql(f"SELECT count(*) as cnt FROM {TABLE}").collect()[0].cnt
    print(f"verification query: {verify:,} rows in table")

    spark.stop()


if __name__ == "__main__":
    main()
