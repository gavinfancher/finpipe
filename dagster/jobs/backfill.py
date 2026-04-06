"""
Dagster job: backfill historical data from Massive S3 into Iceberg.

Flow:
  1. Launch EC2 spot (c5n.4xlarge) via infra.ec2.backfill
  2. SSM: clone repo, install deps, run batch/main.py with CLI args
     → downloads .csv.gz from Massive, stages parquet to S3
  3. Terminate spot instance (always, even on failure)
  4. Submit EMR Serverless job: staged parquet → Iceberg bronze (with --cleanup)

Usage:
    uv run dagster dev -f definitions.py
"""

import sys
import time

import boto3
import pendulum
from dagster import (
    Config,
    OpExecutionContext,
    Out,
    get_dagster_logger,
    job,
    op,
)

from resources.emr import EMRServerlessResource

REPO_URL = "https://github.com/gavinfancher/finpipe.git"
REGION = "us-east-1"
S3_BUCKET = "finpipe-lakehouse"


class BackfillConfig(Config):
    year: int = 2025
    months: list[int] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    workers: int = 16


def _get_infra_imports():
    """Lazy import infra scripts — only available when running from full repo."""
    from infra.ec2.backfill.instance import create as launch_backfill, terminate
    return launch_backfill, terminate


def ssm_run(instance_id, commands, timeout=600):
    """Run shell commands on an instance via SSM. Returns (status, stdout, stderr)."""
    ssm = boto3.client("ssm", region_name=REGION)

    resp = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Parameters={
            "commands": commands,
            "executionTimeout": [str(timeout)],
        },
        TimeoutSeconds=timeout,
    )
    command_id = resp["Command"]["CommandId"]

    while True:
        time.sleep(5)
        result = ssm.get_command_invocation(
            CommandId=command_id,
            InstanceId=instance_id,
        )
        if result["Status"] in ("Success", "Failed", "TimedOut", "Cancelled"):
            return (
                result["Status"],
                result.get("StandardOutputContent", ""),
                result.get("StandardErrorContent", ""),
            )


def wait_for_ssm(instance_id, timeout=300):
    """Wait for the SSM agent to come online."""
    ssm = boto3.client("ssm", region_name=REGION)
    start = time.monotonic()

    while time.monotonic() - start < timeout:
        resp = ssm.describe_instance_information(
            Filters=[{"Key": "InstanceIds", "Values": [instance_id]}],
        )
        instances = resp.get("InstanceInformationList", [])
        if instances and instances[0].get("PingStatus") == "Online":
            return
        time.sleep(10)

    raise TimeoutError(f"SSM agent not online after {timeout}s on {instance_id}")


def log_output(context: OpExecutionContext, stdout: str, stderr: str):
    """Write SSM stdout/stderr to Dagster's captured logs."""
    for line in stdout.strip().splitlines():
        if line.strip():
            print(line)  # noqa: T201 — goes to dagster stdout capture
    for line in stderr.strip().splitlines():
        if line.strip():
            print(line, file=sys.stderr)  # noqa: T201 — goes to dagster stderr capture


@op(out=Out(str))
def stage_backfill(context: OpExecutionContext, config: BackfillConfig) -> str:
    """Launch spot instance, run backfill staging, terminate instance.

    Instance is always terminated, even on failure.
    """
    instance_id = None
    _, terminate = _get_infra_imports()
    launch_backfill, _ = _get_infra_imports()

    try:
        # launch
        ts = pendulum.now().format("YYYY-MM-DD-HH-mm")
        context.log.info("launching backfill spot instance...")
        instance_id, public_ip = launch_backfill(name_suffix=ts)
        context.log.info(f"instance: {instance_id}, ip: {public_ip}")

        # wait for SSM
        context.log.info("waiting for SSM agent...")
        wait_for_ssm(instance_id, timeout=300)
        context.log.info("SSM agent online")

        # clone + install
        context.log.info("cloning repo and installing deps...")
        status, stdout, stderr = ssm_run(instance_id, [
            f"git clone {REPO_URL} /home/ubuntu/finpipe",
        ])
        log_output(context, stdout, stderr)
        if status != "Success":
            raise RuntimeError(f"git clone failed: {stderr}")

        status, stdout, stderr = ssm_run(instance_id, [
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
            "cd /home/ubuntu/finpipe && /root/.local/bin/uv sync",
        ], timeout=120)
        log_output(context, stdout, stderr)
        if status != "Success":
            raise RuntimeError(f"dependency install failed: {stderr}")
        context.log.info("dependencies installed")

        # run backfill
        months_str = " ".join(str(m) for m in config.months)
        context.log.info(f"starting backfill: year={config.year} months={months_str} workers={config.workers}")

        log_file = "/tmp/backfill.log"
        # run backfill with output to file (SSM has 24KB output limit)
        status, stdout, stderr = ssm_run(instance_id, [
            f"cd /home/ubuntu/finpipe && /root/.local/bin/uv run python dagster/batch/main.py"
            f" --year {config.year}"
            f" --months {months_str}"
            f" --mode concurrent"
            f" --workers {config.workers}"
            f" --bucket {S3_BUCKET}"
            f" > {log_file} 2>&1"
            f" ; echo EXIT_CODE=$?",
        ], timeout=3600)

        # fetch log in chunks (SSM has 24KB output limit per invocation)
        offset = 0
        chunk_lines = 200
        while True:
            _, chunk, _ = ssm_run(instance_id, [
                f"sed -n '{offset + 1},{offset + chunk_lines}p' {log_file}",
            ])
            if not chunk.strip():
                break
            for line in chunk.strip().splitlines():
                print(line)
            offset += chunk_lines

        # check if the script succeeded
        if "EXIT_CODE=0" not in stdout:
            raise RuntimeError("backfill script failed — see stdout above")

        context.log.info("backfill staging complete")
        return "success"

    finally:
        if instance_id:
            context.log.info(f"terminating {instance_id}...")
            try:
                terminate(instance_id)
                context.log.info(f"{instance_id} terminated")
            except Exception as e:
                context.log.error(f"failed to terminate {instance_id}: {e}")


@op
def commit_to_iceberg(context: OpExecutionContext, emr: EMRServerlessResource, staging_result: str):
    """Submit EMR job to write staged parquet to Iceberg bronze, then clean up."""
    if staging_result != "success":
        raise RuntimeError("skipping EMR — backfill staging failed")

    script_path = f"s3://{S3_BUCKET}/scripts/staged_to_bronze.py"

    context.log.info("submitting staged→bronze EMR job")
    job_run_id = emr.submit_spark_job(
        script_s3_path=script_path,
        args=["--cleanup"],
        name="finpipe-staged-to-bronze",
    )

    state = emr.wait_for_job(job_run_id)
    context.log.info(f"EMR job complete: {state}")


@job
def backfill_job():
    result = stage_backfill()
    commit_to_iceberg(staging_result=result)
