"""EMR Serverless resource — submits and monitors Spark jobs."""

import logging
import time
from typing import Any

import boto3
from dagster import ConfigurableResource


# Application states where the app still exists and can accept job runs (not torn down).
_EMR_APP_USABLE_STATES = frozenset(
    {"CREATED", "STARTING", "STARTED", "STOPPED", "STOPPING", "UPDATING"}
)


class EMRServerlessResource(ConfigurableResource):
    """Submit PySpark jobs to EMR Serverless and wait for completion."""

    application_id: str = ""
    execution_role_arn: str = ""
    region: str = "us-east-1"
    s3_bucket: str = "finpipe-lakehouse"
    app_name: str = "finpipe-spark"

    def _client(self):
        return boto3.client("emr-serverless", region_name=self.region)

    def _list_all_applications(self) -> list[dict]:
        """Paginate — list_applications is not a single page."""
        client = self._client()
        paginator = client.get_paginator("list_applications")
        out: list[dict] = []
        for page in paginator.paginate():
            out.extend(page.get("applications", []))
        return out

    def _resolve_application_id(self) -> str:
        """Return configured id, otherwise look up by app_name in this region."""
        configured = str(self.application_id).strip() if self.application_id else ""
        if configured:
            return configured

        apps = self._list_all_applications()
        for app in apps:
            if app["name"] == self.app_name and app.get("state") in _EMR_APP_USABLE_STATES:
                return app["id"]

        names = sorted({a.get("name", "?") for a in apps})
        preview = names[:25]
        suffix = " …" if len(names) > 25 else ""
        raise RuntimeError(
            f"no EMR Serverless application named {self.app_name!r} in region {self.region!r}. "
            "Create one: uv run python infra/emr/application.py "
            f"(from repo root), or set EMR_APPLICATION_ID / secret finpipe/emr-application-id "
            f"to the application UUID, or EMR_APP_NAME if the app uses a different name. "
            f"Applications visible in this account/region: {preview}{suffix}"
        )

    def submit_spark_job(
        self,
        script_s3_path: str,
        args: list[str] | None = None,
        spark_config: dict[str, str] | None = None,
        spark_cli_prefix: str | None = None,
        name: str = "finpipe-spark-job",
        log: Any | None = None,
    ) -> tuple[str, str]:
        """Submit a PySpark job. Returns ``(job_run_id, application_id)``.

        Pass ``context.log`` from an op or asset so messages appear in the Dagster UI.

        ``spark_cli_prefix``: optional ``spark-submit`` flags placed *before* ``--conf``
        (e.g. ``--num-executors 2 --executor-memory 14G``). EMR Serverless sometimes
        applies these more reliably than ``spark.executor.instances`` alone.
        """
        _log = log if log is not None else logging.getLogger(__name__)
        client = self._client()

        # default Spark properties for Iceberg + Glue
        # EMR 7.x ships Iceberg natively — use the bundled JAR, no Maven downloads
        # EMR Serverless app maximumCapacity (e.g. 8 vCPU / 32 GB) includes driver + executors;
        # disable dynamic allocation and cap executors so small apps do not hit
        # ApplicationMaxCapacityExceededException.
        default_config = {
            "spark.jars": "/usr/share/aws/iceberg/lib/iceberg-spark3-runtime.jar",
            "spark.sql.catalog.glue": "org.apache.iceberg.spark.SparkCatalog",
            "spark.sql.catalog.glue.catalog-impl": "org.apache.iceberg.aws.glue.GlueCatalog",
            "spark.sql.catalog.glue.warehouse": f"s3://{self.s3_bucket}/iceberg/",
            "spark.sql.catalog.glue.io-impl": "org.apache.iceberg.aws.s3.S3FileIO",
            "spark.sql.extensions": "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
            "spark.sql.defaultCatalog": "glue",
            "spark.dynamicAllocation.enabled": "false",
            "spark.executor.instances": "1",
            "spark.executor.cores": "2",
            "spark.executor.memory": "6g",
            "spark.driver.cores": "1",
            "spark.driver.memory": "4g",
        }
        if spark_config:
            default_config.update(spark_config)

        conf_args = " ".join(f"--conf {k}={v}" for k, v in default_config.items())
        spark_submit_parameters = (
            f"{spark_cli_prefix.strip()} {conf_args}"
            if spark_cli_prefix
            else conf_args
        )

        job_driver = {
            "sparkSubmit": {
                "entryPoint": script_s3_path,
                "sparkSubmitParameters": spark_submit_parameters,
            },
        }
        if args:
            job_driver["sparkSubmit"]["entryPointArguments"] = args

        application_id = self._resolve_application_id()
        resp = client.start_job_run(
            applicationId=application_id,
            executionRoleArn=self.execution_role_arn,
            jobDriver=job_driver,
            name=name,
            tags={"project": "finpipe"},
        )
        job_run_id = resp["jobRunId"]
        _log.info("submitted EMR job: %s (%s) app=%s", job_run_id, name, application_id)
        return job_run_id, application_id

    def wait_for_job(
        self,
        job_run_id: str,
        poll_interval: int = 15,
        log: Any | None = None,
        application_id: str | None = None,
    ) -> str:
        """Poll until job completes. Returns final state.

        Pass ``application_id`` from ``submit_spark_job`` so polling does not call
        ``list_applications`` again (and stays consistent if settings change mid-run).
        """
        _log = log if log is not None else logging.getLogger(__name__)
        client = self._client()
        app_id = (
            str(application_id).strip()
            if application_id and str(application_id).strip()
            else self._resolve_application_id()
        )

        while True:
            resp = client.get_job_run(
                applicationId=app_id,
                jobRunId=job_run_id,
            )
            state = resp["jobRun"]["state"]

            if state in ("SUCCESS",):
                _log.info("EMR job %s completed successfully", job_run_id)
                return state
            elif state in ("FAILED", "CANCELLED"):
                details = resp["jobRun"].get("stateDetails", "no details")
                raise RuntimeError(f"EMR job {job_run_id} {state}: {details}")

            _log.info("EMR job %s: %s", job_run_id, state)
            time.sleep(poll_interval)
