"""
Dagster job: backfill historical data from Massive S3 into Iceberg.

Steps (each visible in Dagster UI):
  1. launch_spot       — launch c5n.4xlarge spot instance
  2. setup_instance    — wait for SSM, clone repo, install deps
  3. run_staging       — run batch/main.py → stage parquet to S3
  4. teardown_spot     — terminate instance
  5. commit_to_iceberg — EMR Serverless: staged parquet → Iceberg bronze

Cleanup: a run status sensor (backfill_cleanup_sensor) monitors for failed runs
and terminates any orphaned spot instances tagged with project=finpipe.

Usage:
    Trigger from Dagster UI with config:
      year: 2025
      months: [1, 2, 3]
      workers: 16
"""

import time

import boto3
import pendulum
from dagster import (
    Config,
    DagsterRunStatus,
    In,
    Nothing,
    OpExecutionContext,
    Out,
    RunStatusSensorContext,
    graph,
    op,
    run_status_sensor,
)

from resources.emr import EMRServerlessResource

REPO_URL = "https://github.com/gavinfancher/finpipe.git"
REGION = "us-east-1"
S3_BUCKET = "finpipe-lakehouse"


class BackfillConfig(Config):
    year: int = 2025
    months: list[int] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    workers: int = 16


# ---------- helpers ----------


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


def log_ssm(context: OpExecutionContext, stdout: str, stderr: str):
    """Log SSM output to Dagster event log."""
    for line in stdout.strip().splitlines():
        if line.strip():
            context.log.info(line)
    for line in stderr.strip().splitlines():
        if line.strip():
            context.log.warning(line)


def fetch_remote_log(context: OpExecutionContext, instance_id: str, log_file: str):
    """Fetch a remote log file in chunks (SSM has 24KB output limit)."""
    offset = 0
    chunk = 200
    while True:
        _, out, _ = ssm_run(instance_id, [
            f"sed -n '{offset + 1},{offset + chunk}p' {log_file}",
        ])
        if not out.strip():
            break
        for line in out.strip().splitlines():
            context.log.info(line)
        offset += chunk


# ---------- ops ----------


@op(out=Out(str))
def launch_spot(context: OpExecutionContext) -> str:
    """Launch a c5n.4xlarge spot instance for backfill."""
    from infra.ec2.backfill.instance import create as launch_backfill

    ts = pendulum.now().format("YYYY-MM-DD-HH-mm")
    context.log.info("launching backfill spot instance...")
    instance_id, public_ip = launch_backfill(name_suffix=ts)
    context.log.info(f"instance: {instance_id}, ip: {public_ip}")
    return instance_id


@op(out={"setup_done": Out(Nothing)})
def setup_instance(context: OpExecutionContext, instance_id: str):
    """Wait for SSM, clone repo, install dependencies."""
    context.log.info("waiting for SSM agent...")
    wait_for_ssm(instance_id, timeout=300)
    context.log.info("SSM agent online")

    context.log.info("cloning repo...")
    status, stdout, stderr = ssm_run(instance_id, [
        f"git clone {REPO_URL} /home/ubuntu/finpipe",
    ])
    log_ssm(context, stdout, stderr)
    if status != "Success":
        raise RuntimeError(f"git clone failed ({status}): {stderr[:500]}")

    context.log.info("installing uv and dependencies...")
    status, stdout, stderr = ssm_run(instance_id, [
        "curl -LsSf https://astral.sh/uv/install.sh | sh",
        "cd /home/ubuntu/finpipe && /root/.local/bin/uv sync --all-packages",
    ], timeout=180)
    log_ssm(context, stdout, stderr)
    if status != "Success":
        raise RuntimeError(f"dependency install failed ({status}): {stderr[:500]}")
    context.log.info("setup complete")


@op(ins={"setup_done": In(Nothing)}, out=Out(str))
def run_staging(context: OpExecutionContext, config: BackfillConfig, instance_id: str) -> str:
    """Run batch/main.py on the spot instance. Stages parquet to S3."""
    months_str = " ".join(str(m) for m in config.months)
    log_file = "/tmp/backfill.log"

    context.log.info(f"backfill: year={config.year} months={months_str} workers={config.workers}")

    status, stdout, stderr = ssm_run(instance_id, [
        f"cd /home/ubuntu/finpipe && /root/.local/bin/uv run python dagster/batch/main.py"
        f" --year {config.year}"
        f" --months {months_str}"
        f" --mode concurrent"
        f" --workers {config.workers}"
        f" --bucket {S3_BUCKET}"
        f" > {log_file} 2>&1"
        f" ; echo BACKFILL_EXIT=$?",
    ], timeout=3600)

    context.log.info(f"SSM status={status}")
    if stdout.strip():
        context.log.info(f"SSM stdout: {stdout.strip()}")

    fetch_remote_log(context, instance_id, log_file)

    if "BACKFILL_EXIT=0" not in stdout:
        raise RuntimeError("backfill staging failed — see logs above")

    context.log.info("staging complete")
    return instance_id


@op
def teardown_spot(context: OpExecutionContext, instance_id: str):
    """Terminate the spot instance."""
    ec2 = boto3.client("ec2", region_name=REGION)
    context.log.info(f"terminating {instance_id}...")
    ec2.terminate_instances(InstanceIds=[instance_id])
    context.log.info(f"{instance_id} terminated")


@op
def commit_to_iceberg(context: OpExecutionContext, emr: EMRServerlessResource, instance_id: str):
    """Submit EMR job: staged parquet → Iceberg bronze table."""
    script_path = f"s3://{S3_BUCKET}/scripts/staged_to_bronze.py"
    context.log.info("submitting staged→bronze EMR job")
    job_run_id = emr.submit_spark_job(
        script_s3_path=script_path,
        args=["--cleanup"],
        name="finpipe-staged-to-bronze",
    )
    state = emr.wait_for_job(job_run_id)
    context.log.info(f"EMR job complete: {state}")


# ---------- graph + job ----------


@graph
def backfill_graph():
    instance_id = launch_spot()
    setup_done = setup_instance(instance_id=instance_id)
    staged_instance_id = run_staging(instance_id=instance_id, setup_done=setup_done)
    teardown_spot(instance_id=staged_instance_id)
    commit_to_iceberg(instance_id=staged_instance_id)


backfill_job = backfill_graph.to_job(name="backfill_job")


# ---------- cleanup sensor ----------


@run_status_sensor(
    run_status=DagsterRunStatus.FAILURE,
    name="backfill_cleanup_sensor",
    monitored_jobs=[backfill_job],
)
def backfill_cleanup_sensor(context: RunStatusSensorContext):
    """Terminate any orphaned backfill spot instances on job failure."""
    ec2 = boto3.client("ec2", region_name=REGION)

    resp = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": ["finpipe-backfill*"]},
            {"Name": "instance-state-name", "Values": ["running", "pending"]},
        ],
    )

    for reservation in resp.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            iid = instance["InstanceId"]
            context.log.info(f"terminating orphaned backfill instance: {iid}")
            ec2.terminate_instances(InstanceIds=[iid])
