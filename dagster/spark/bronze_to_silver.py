"""
PySpark job: bronze → silver transform.

Reads from Iceberg bronze table, enriches with timestamps and session
classification, writes to Iceberg silver table via Glue catalog.

Runs on EMR Serverless — submitted by the Dagster silver_minute_aggs asset.

Usage (local testing):
    spark-submit bronze_to_silver.py
"""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


BRONZE_TABLE = "glue.finpipe_bronze.equities_minute_aggs"
SILVER_TABLE = "glue.finpipe_silver.equities_minute_aggs"


def add_timestamp(df):
    """Convert nanosecond window_start to Eastern datetime."""
    return df.withColumn(
        "timestamp",
        F.from_utc_timestamp(
            (F.col("window_start") / 1e9).cast("timestamp"),
            "America/New_York",
        ),
    )


def add_market_session(df):
    """Classify each bar by market session based on Eastern time."""
    time_minutes = F.hour("timestamp") * 60 + F.minute("timestamp")
    return df.withColumn(
        "session",
        F.when((time_minutes >= 4 * 60) & (time_minutes < 9 * 60 + 30), "pre_market")
        .when((time_minutes >= 9 * 60 + 30) & (time_minutes < 16 * 60), "market")
        .when((time_minutes >= 16 * 60) & (time_minutes < 20 * 60), "post_market")
        .otherwise("closed"),
    )


def main():
    spark = SparkSession.builder.appName("finpipe-bronze-to-silver").getOrCreate()

    df = spark.table(BRONZE_TABLE)
    row_count = df.count()
    print(f"read {row_count:,} rows from {BRONZE_TABLE}")

    if row_count == 0:
        print("no data to process")
        spark.stop()
        return

    # enrich
    df = add_timestamp(df)
    df = add_market_session(df)

    # write to iceberg
    if spark.catalog.tableExists(SILVER_TABLE):
        df.writeTo(SILVER_TABLE).overwritePartitions()
        print(f"overwrote partitions in {SILVER_TABLE}")
    else:
        (
            df.writeTo(SILVER_TABLE)
            .partitionedBy("date", "ticker")
            .create()
        )
        print(f"created {SILVER_TABLE}")

    print(f"wrote {row_count:,} rows to {SILVER_TABLE}")
    spark.stop()


if __name__ == "__main__":
    main()
