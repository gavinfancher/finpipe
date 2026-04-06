"""EMR Serverless resource — submits and monitors Spark jobs."""

import os
import time

import boto3
from dagster import ConfigurableResource, get_dagster_logger


class EMRServerlessResource(ConfigurableResource):
    """Submit PySpark jobs to EMR Serverless and wait for completion."""

    application_id: str = ""
    execution_role_arn: str = ""
    region: str = "us-east-1"
    s3_bucket: str = "finpipe-lakehouse"

    def _client(self):
        return boto3.client("emr-serverless", region_name=self.region)

    def submit_spark_job(
        self,
        script_s3_path: str,
        args: list[str] | None = None,
        spark_config: dict[str, str] | None = None,
        name: str = "finpipe-spark-job",
    ) -> str:
        """Submit a PySpark job. Returns the job run ID."""
        log = get_dagster_logger()
        client = self._client()

        # default Spark properties for Iceberg + Glue
        # EMR 7.1 ships Iceberg natively — use the bundled JAR, no Maven downloads
        default_config = {
            "spark.jars": "/usr/share/aws/iceberg/lib/iceberg-spark3-runtime.jar",
            "spark.sql.catalog.glue": "org.apache.iceberg.spark.SparkCatalog",
            "spark.sql.catalog.glue.catalog-impl": "org.apache.iceberg.aws.glue.GlueCatalog",
            "spark.sql.catalog.glue.warehouse": f"s3://{self.s3_bucket}/iceberg/",
            "spark.sql.catalog.glue.io-impl": "org.apache.iceberg.aws.s3.S3FileIO",
            "spark.sql.extensions": "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
            "spark.sql.defaultCatalog": "glue",
        }
        if spark_config:
            default_config.update(spark_config)

        job_driver = {
            "sparkSubmit": {
                "entryPoint": script_s3_path,
                "sparkSubmitParameters": " ".join(
                    f"--conf {k}={v}" for k, v in default_config.items()
                ),
            },
        }
        if args:
            job_driver["sparkSubmit"]["entryPointArguments"] = args

        resp = client.start_job_run(
            applicationId=self.application_id,
            executionRoleArn=self.execution_role_arn,
            jobDriver=job_driver,
            name=name,
            tags={"project": "finpipe"},
        )
        job_run_id = resp["jobRunId"]
        log.info("submitted EMR job: %s (%s)", job_run_id, name)
        return job_run_id

    def wait_for_job(self, job_run_id: str, poll_interval: int = 15) -> str:
        """Poll until job completes. Returns final state."""
        log = get_dagster_logger()
        client = self._client()

        while True:
            resp = client.get_job_run(
                applicationId=self.application_id,
                jobRunId=job_run_id,
            )
            state = resp["jobRun"]["state"]

            if state in ("SUCCESS",):
                log.info("EMR job %s completed successfully", job_run_id)
                return state
            elif state in ("FAILED", "CANCELLED"):
                details = resp["jobRun"].get("stateDetails", "no details")
                raise RuntimeError(f"EMR job {job_run_id} {state}: {details}")

            log.info("EMR job %s: %s", job_run_id, state)
            time.sleep(poll_interval)
