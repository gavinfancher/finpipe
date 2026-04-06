"""
Bronze asset: ingest minute agg files from Massive S3 into Iceberg.

Daily ingest (single file, ~40-100 MB):
  Massive S3 → PyArrow → PyIceberg → Glue/Iceberg (no Spark needed)

Backfill (200+ files, concurrent):
  Handled separately — batch/main.py stages to S3, then EMR writes to Iceberg.
"""

import gzip
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pa_csv
from dagster import (
    AssetExecutionContext,
    Config as DagsterConfig,
    MaterializeResult,
    MetadataValue,
    asset,
)

from common.schemas import BRONZE_SCHEMA, CSV_CONVERT_OPTS, CSV_READ_OPTS, MASSIVE_COLUMNS
from resources.massive_s3 import MassiveS3Resource

S3_BUCKET = "finpipe-lakehouse"
ICEBERG_TABLE = "finpipe_bronze.equities_minute_aggs"


class BronzeIngestConfig(DagsterConfig):
    file_key: str


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


def _get_iceberg_table():
    """Load the Iceberg table via PyIceberg + Glue catalog."""
    from pyiceberg.catalog.glue import GlueCatalog

    catalog = GlueCatalog("glue", **{"s3.region": "us-east-1"})

    db, tbl = ICEBERG_TABLE.split(".")
    if not catalog.table_exists((db, tbl)):
        catalog.create_table(
            identifier=(db, tbl),
            schema=BRONZE_SCHEMA,
            partition_spec=[("date",)],
            location=f"s3://{S3_BUCKET}/iceberg/{db}/{tbl}",
        )

    return catalog.load_table((db, tbl))


@asset(
    name="bronze_minute_aggs",
    group_name="bronze",
    compute_kind="pyiceberg",
)
def bronze_minute_aggs(
    context: AssetExecutionContext,
    config: BronzeIngestConfig,
    massive_s3: MassiveS3Resource,
) -> MaterializeResult:
    """Download a .csv.gz from Massive and write directly to Iceberg."""
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

    # write directly to Iceberg
    t1 = time.monotonic()
    iceberg_table = _get_iceberg_table()
    iceberg_table.append(table)
    write_time = time.monotonic() - t1
    context.log.info("wrote to %s (%.1fs)", ICEBERG_TABLE, write_time)

    return MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(len(table)),
            "date": MetadataValue.text(date_str),
            "source_file": MetadataValue.text(file_key),
            "iceberg_table": MetadataValue.text(ICEBERG_TABLE),
            "parse_seconds": MetadataValue.float(parse_time),
            "write_seconds": MetadataValue.float(write_time),
        },
    )
