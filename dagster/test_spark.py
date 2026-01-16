#!/usr/bin/env python3


import os
from pathlib import Path

from dotenv import load_dotenv
from pyspark.sql import SparkSession

# Load environment
load_dotenv(Path(__file__).parent / ".env")


def get_spark_session(app_name: str = "spark-test") -> SparkSession:
    """Connect to the remote Spark Connect server."""
    spark_host = os.getenv("SPARK_HOST")
    spark_port = os.getenv("SPARK_PORT")
    
    print(f"Connecting to Spark at sc://{spark_host}:{spark_port}")
    
    return (
        SparkSession.builder
        .remote(f"sc://{spark_host}:{spark_port}")
        .appName(app_name)
        .getOrCreate()
    )


def test_spark_massive():
    """Test Spark reading directly from Massive S3 (flatfiles bucket)."""

    
    session = get_spark_session("test-massive")
    
    try:
        # explicit file object keys for testing that we know exist
        massive_path = "s3a://flatfiles/us_stocks_sip/minute_aggs_v1/2026/01/2026-01-15.csv.gz"
        print(f"Reading: {massive_path}")
        
        df = (
            session.read
            .option("header", "true")
            .option("inferSchema", "true")
            .csv(massive_path)
        )
        
        count = df.count()
        print(f"SUCCESS: Read {count:,} rows from Massive S3")
        df.show(3)
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"FAILED: {type(e).__name__}")
        
        if "403" in error_msg or "Forbidden" in error_msg:
            print("  -> Authentication failed - check MASSIVE_ACCESS_KEY/SECRET_KEY")
        elif "NoSuchBucket" in error_msg:
            print("  -> Bucket 'flatfiles' not found at configured endpoint")
        elif "UnknownHost" in error_msg:
            print("  -> Cannot reach files.massive.com - check network/DNS")
        else:
            print(f"  -> {error_msg[:300]}")
        
        return False
        
    finally:
        session.stop()


def test_spark_iceberg_read():
    """Test Spark reading from existing Iceberg table."""
    print("\n" + "=" * 60)
    print("Test: Spark -> Iceberg (read bronze.minute_aggs)")
    print("=" * 60)
    
    session = get_spark_session("test-iceberg")
    
    try:
        print("Reading from iceberg.bronze.minute_aggs...")
        
        # Use table() API instead of SQL - works better with Spark Connect
        df = session.read.table("iceberg.bronze.minute_aggs")
        count = df.count()
        print(f"SUCCESS: Read {count:,} rows from Iceberg")
        df.show(3)
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"FAILED: {type(e).__name__}")
        
        if "NoSuchNamespaceException" in error_msg:
            print("  -> Namespace 'bronze' doesn't exist. Create it with:")
            print("     docker exec spark-iceberg spark-sql -e 'CREATE NAMESPACE IF NOT EXISTS iceberg.bronze'")
        elif "NoSuchTableException" in error_msg or "TABLE_OR_VIEW_NOT_FOUND" in error_msg:
            print("  -> Table 'minute_aggs' doesn't exist yet - run the Dagster job first")
        else:
            print(f"  -> {error_msg[:300]}")
        
        return False
        
    finally:
        session.stop()


def test_spark_iceberg_write():
    """Test Spark writing to Iceberg table (end-to-end test)."""
    print("\n" + "=" * 60)
    print("Test: Spark -> Iceberg Write (Massive -> Iceberg)")
    print("=" * 60)
    
    session = get_spark_session("test-iceberg-write")
    
    try:
        # Read a small sample from Massive S3
        massive_path = "s3a://flatfiles/us_stocks_sip/minute_aggs_v1/2026/01/2026-01-14.csv.gz"
        print(f"Reading from {massive_path}...")
        
        df = (
            session.read
            .option("header", "true")
            .option("inferSchema", "true")
            .csv(massive_path)
            .limit(100)  # Just 100 rows for the test
        )
        
        # Add a test partition column
        from pyspark.sql.functions import lit
        df = df.withColumn("date", lit("2026-01-14"))
        
        print("Writing to iceberg.bronze.test_minute_aggs...")
        
        (
            df.writeTo("iceberg.bronze.test_minute_aggs")
            .tableProperty("write.format.default", "parquet")
            .partitionedBy("date")
            .createOrReplace()
        )
        
        # Read it back
        result = session.read.table("iceberg.bronze.test_minute_aggs")
        count = result.count()
        print(f"SUCCESS: Wrote and read back {count} rows")
        result.show(3)
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"FAILED: {type(e).__name__}")
        
        if "NoSuchNamespaceException" in error_msg:
            print("  -> Namespace 'bronze' doesn't exist. Create it with:")
            print("     docker exec spark-iceberg spark-sql -e 'CREATE NAMESPACE IF NOT EXISTS iceberg.bronze'")
        else:
            print(f"  -> {error_msg[:300]}")
        
        return False
        
    finally:
        session.stop()


if __name__ == "__main__":
    print("=" * 60)
    print("Spark Connectivity Tests")
    print("=" * 60)
    
    results = {}
    
    # Test 1: Spark -> Massive S3 (main use case)
    results["massive_s3"] = test_spark_massive()
    
    # Test 2: Spark -> Iceberg Catalog
    results["iceberg_catalog"] = test_spark_iceberg_catalog()
    
    # Test 3: Spark -> Iceberg Table (if exists)
    results["iceberg_table"] = test_spark_iceberg_read()
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    for test, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test}: {status}")
