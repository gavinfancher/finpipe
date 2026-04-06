"""
Daily lakehouse job: ingest new files from Massive → stage to S3 → transform via EMR.

Can be triggered by the daily_ingest_sensor or run manually.
"""

from dagster import AssetKey, define_asset_job

daily_lakehouse_job = define_asset_job(
    name="daily_lakehouse_job",
    selection=[AssetKey("bronze_minute_aggs"), AssetKey("silver_minute_aggs")],
)
