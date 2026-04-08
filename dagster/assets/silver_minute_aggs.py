"""
Silver asset: enrich bronze minute aggs via EMR Serverless.

Reads from Iceberg bronze table, adds timestamps and session classification,
writes to Iceberg silver table via Glue catalog.

iceberg/finpipe_bronze/equities_minute_aggs → EMR (PySpark) → iceberg/finpipe_silver/equities_minute_aggs
"""

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from resources.emr import EMRServerlessResource

S3_BUCKET = "finpipe-lakehouse"
SCRIPT_S3_PATH = f"s3://{S3_BUCKET}/scripts/bronze_to_silver.py"


@asset(
    name="silver_minute_aggs",
    group_name="silver",
    compute_kind="spark",
    deps=["bronze_minute_aggs"],
)
def silver_minute_aggs(
    context: AssetExecutionContext,
    emr: EMRServerlessResource,
) -> MaterializeResult:
    """Submit bronze→silver transform to EMR Serverless and wait for completion."""
    context.log.info("submitting bronze→silver transform to EMR Serverless")

    job_run_id = emr.submit_spark_job(
        script_s3_path=SCRIPT_S3_PATH,
        name="finpipe-bronze-to-silver",
        log=context.log,
    )

    state = emr.wait_for_job(job_run_id, log=context.log)

    return MaterializeResult(
        metadata={
            "job_run_id": MetadataValue.text(job_run_id),
            "state": MetadataValue.text(state),
            "script": MetadataValue.text(SCRIPT_S3_PATH),
        },
    )
