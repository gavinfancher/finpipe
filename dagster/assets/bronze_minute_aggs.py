"""
Bronze asset: ingest daily minute agg files from Massive S3.

Downloads .csv.gz → PyArrow → parquet → s3://finpipe-lakehouse/bronze/staged/

For daily ingest: runs on a t3.small spot instance (40-100 MB files).
For backfill: reuses the existing backfill job with c5n.4xlarge.
"""

import gzip
import io
import time
from pathlib import Path

import boto3
import pyarrow.csv as pa_csv
import pyarrow.parquet as pq
from botocore.config import Config
from dagster import (
    AssetExecutionContext,
    Config as DagsterConfig,
    MaterializeResult,
    MetadataValue,
    asset,
)

from common.schemas import BRONZE_SCHEMA, CSV_CONVERT_OPTS, CSV_READ_OPTS, MASSIVE_COLUMNS
from resources.massive_s3 import MassiveS3Resource

import pyarrow as pa

S3_BUCKET = "finpipe-lakehouse"


class BronzeIngestConfig(DagsterConfig):
    file_key: str
    overwrite: bool = False


def _cast_to_schema(table, date_str):
    """Cast raw CSV table to bronze schema, adding date column."""
    columns = {}
    for col in MASSIVE_COLUMNS:
        if col in table.column_names:
            columns[col] = table.column(col)
        else:
            columns[col] = pa.nulls(len(table), type=BRONZE_SCHEMA.field(col).type)
    columns["date"] = pa.array([date_str] * len(table), type=pa.string())
    return pa.table(columns).cast(BRONZE_SCHEMA)


@asset(
    name="bronze_minute_aggs",
    group_name="bronze",
    compute_kind="pyarrow",
)
def bronze_minute_aggs(
    context: AssetExecutionContext,
    config: BronzeIngestConfig,
    massive_s3: MassiveS3Resource,
) -> MaterializeResult:
    """Download a .csv.gz from Massive, convert to parquet, stage to S3."""
    file_key = config.file_key
    date_str = Path(file_key).name.replace(".csv.gz", "")
    context.log.info("ingesting %s (date=%s)", file_key, date_str)

    # download and parse
    t0 = time.monotonic()
    client = massive_s3.get_client()
    resp = client.get_object(Bucket="flatfiles", Key=file_key)
    with gzip.GzipFile(fileobj=resp["Body"]) as gz:
        table = pa_csv.read_csv(gz, convert_options=CSV_CONVERT_OPTS, read_options=CSV_READ_OPTS)
    table = _cast_to_schema(table, date_str)
    parse_time = time.monotonic() - t0
    context.log.info("parsed %d rows in %.1fs", len(table), parse_time)

    # write parquet to S3
    t1 = time.monotonic()
    buf = io.BytesIO()
    pq.write_table(table, buf)
    s3_key = f"bronze/staged/{date_str}.parquet"

    s3 = boto3.client("s3", region_name="us-east-1")
    s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=buf.getvalue())
    upload_time = time.monotonic() - t1
    context.log.info("staged s3://%s/%s (%.1fs)", S3_BUCKET, s3_key, upload_time)

    return MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(len(table)),
            "date": MetadataValue.text(date_str),
            "source_file": MetadataValue.text(file_key),
            "s3_path": MetadataValue.text(f"s3://{S3_BUCKET}/{s3_key}"),
            "parse_seconds": MetadataValue.float(parse_time),
            "upload_seconds": MetadataValue.float(upload_time),
        },
    )
