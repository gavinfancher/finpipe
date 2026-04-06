"""
Dagster job: backfill historical data from Massive S3 into Iceberg.

Flow:
  1. Launch EC2 spot (c5n.4xlarge) via infra.ec2.backfill
  2. SSM: clone repo, install deps, run batch/main.py with CLI args
     → downloads .csv.gz from Massive, stages parquet to S3
  3. Terminate spot instance
  4. Submit EMR Serverless job: staged parquet → Iceberg bronze (with --cleanup)

The batch step accepts --year and --months args so you can backfill
incrementally without doing everything at once.

Usage:
    uv run dagster dev -f definitions.py
"""

import time

import boto3
import pendulum
from dagster import (
    Config,
    In,
    Nothing,
    Out,
    get_dagster_logger,
    graph,
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


def ssm_run(instance_id, commands, timeout=600, log_fn=None):
    """Run shell commands on an instance via SSM. Polls and streams output."""
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

    last_stdout_len = 0
    last_stderr_len = 0

    while True:
        time.sleep(5)
        result = ssm.get_command_invocation(
            CommandId=command_id,
            InstanceId=instance_id,
        )
        status = result["Status"]

        if log_fn:
            stdout = result.get("StandardOutputContent", "")
            stderr = result.get("StandardErrorContent", "")

            if len(stdout) > last_stdout_len:
                for line in stdout[last_stdout_len:].strip().split("\n"):
                    if line.strip():
                        log_fn("info", line)
                last_stdout_len = len(stdout)

            if len(stderr) > last_stderr_len:
                for line in stderr[last_stderr_len:].strip().split("\n"):
                    if line.strip():
                        log_fn("warning", line)
                last_stderr_len = len(stderr)

        if status in ("Success", "Failed", "TimedOut", "Cancelled"):
            stdout = result.get("StandardOutputContent", "")
            stderr = result.get("StandardErrorContent", "")
            return status, stdout, stderr


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


# ---------- ops ----------


@op(out={"instance_id": Out(str)})
def launch_instance():
    """Launch EC2 spot instance for backfill."""
    log = get_dagster_logger()

    log.info("launching backfill spot instance...")
    launch_backfill, _ = _get_infra_imports()
    ts = pendulum.now().format("YYYY-MM-DD-HH-mm")
    instance_id, public_ip = launch_backfill(name_suffix=ts)
    log.info("instance id: %s, ip: %s", instance_id, public_ip)

    return instance_id


@op(out={"ssm_ready": Out(Nothing)})
def wait_for_ssm_agent(instance_id: str):
    """Wait for the SSM agent to register and come online."""
    log = get_dagster_logger()
    log.info("waiting for SSM agent on %s...", instance_id)

    start = time.monotonic()
    wait_for_ssm(instance_id, timeout=300)
    log.info("SSM agent online (%.0fs)", time.monotonic() - start)


@op(
    ins={"ssm_ready": In(Nothing)},
    out={"code_ready": Out(Nothing)},
)
def pull_code(instance_id: str):
    """Clone repo and install dependencies via SSM."""
    log = get_dagster_logger()

    def log_fn(level, msg):
        getattr(log, level)(msg)

    log.info("cloning %s", REPO_URL)
    status, _, stderr = ssm_run(instance_id, [
        f"git clone {REPO_URL} /home/ubuntu/finpipe",
    ], log_fn=log_fn)
    if status != "Success":
        raise RuntimeError(f"git clone failed: {stderr}")

    log.info("installing uv and dependencies")
    status, _, stderr = ssm_run(instance_id, [
        "curl -LsSf https://astral.sh/uv/install.sh | sh",
        "cd /home/ubuntu/finpipe && /root/.local/bin/uv sync",
    ], timeout=120, log_fn=log_fn)
    if status != "Success":
        raise RuntimeError(f"dependency install failed: {stderr}")
    log.info("dependencies installed")


@op(ins={"code_ready": In(Nothing)}, out=Out(str))
def run_backfill(config: BackfillConfig, instance_id: str) -> str:
    """Run batch/main.py on the spot instance via SSM.

    Stages parquet files to s3://finpipe-lakehouse/bronze/staged/
    """
    log = get_dagster_logger()
    months_str = " ".join(str(m) for m in config.months)
    log_file = "/tmp/backfill.log"
    pid_file = "/tmp/backfill.pid"

    log.info("starting backfill: year=%d months=%s workers=%d",
             config.year, months_str, config.workers)

    try:
        cmd = (
            f"cd /home/ubuntu/finpipe && /root/.local/bin/uv run python dagster/batch/main.py"
            f" --year {config.year}"
            f" --months {months_str}"
            f" --mode concurrent"
            f" --workers {config.workers}"
            f" --bucket {S3_BUCKET}"
            f" --prefix ''"
            f" > {log_file} 2>&1 & echo $! > {pid_file}"
        )
        status, _, stderr = ssm_run(instance_id, [cmd])
        if status != "Success":
            log.error("failed to launch backfill: %s", stderr)
            return "failed"

        # poll log file for output
        last_line_count = 0
        while True:
            time.sleep(10)

            check_status, stdout, _ = ssm_run(instance_id, [
                f"cat {pid_file} | xargs ps -p > /dev/null 2>&1 && echo RUNNING || echo DONE",
                f"wc -l < {log_file}",
                f"tail -n +{last_line_count + 1} {log_file}",
            ])

            if check_status != "Success":
                log.warning("failed to poll instance")
                continue

            lines = stdout.strip().split("\n")
            if len(lines) >= 3:
                proc_status = lines[0].strip()
                new_output = "\n".join(lines[2:]).strip()

                if new_output:
                    for line in new_output.split("\n"):
                        if line.strip():
                            log.info(line)

                try:
                    last_line_count = int(lines[1].strip())
                except ValueError:
                    pass

                if proc_status == "DONE":
                    log.info("backfill staging complete")
                    _, final_out, _ = ssm_run(instance_id, [
                        f"tail -n +{last_line_count + 1} {log_file}",
                    ])
                    if final_out and final_out.strip():
                        for line in final_out.strip().split("\n"):
                            if line.strip():
                                log.info(line)
                    return "success"

    except Exception as e:
        log.error("backfill error: %s", e)
        return "failed"


@op
def terminate_instance(instance_id: str, backfill_result: str):
    """Terminate the spot instance. Always runs."""
    log = get_dagster_logger()

    _, terminate = _get_infra_imports()
    log.info("terminating %s...", instance_id)
    terminate(instance_id)
    log.info("%s terminated", instance_id)

    if backfill_result != "success":
        raise RuntimeError("backfill staging failed — instance terminated, check logs above")


@op
def commit_to_iceberg(emr: EMRServerlessResource, backfill_result: str):
    """Submit EMR job to write staged parquet to Iceberg bronze, then clean up."""
    if backfill_result != "success":
        raise RuntimeError("skipping EMR — backfill staging failed")

    log = get_dagster_logger()
    script_path = f"s3://{S3_BUCKET}/scripts/staged_to_bronze.py"

    log.info("submitting staged→bronze EMR job")
    job_run_id = emr.submit_spark_job(
        script_s3_path=script_path,
        args=["--cleanup"],
        name="finpipe-staged-to-bronze",
    )

    state = emr.wait_for_job(job_run_id)
    log.info("EMR job complete: %s", state)


@graph
def backfill_graph():
    instance_id = launch_instance()
    ssm_ready = wait_for_ssm_agent(instance_id=instance_id)
    code_ready = pull_code(instance_id=instance_id, ssm_ready=ssm_ready)
    backfill_result = run_backfill(instance_id=instance_id, code_ready=code_ready)
    terminate_instance(instance_id=instance_id, backfill_result=backfill_result)
    commit_to_iceberg(backfill_result=backfill_result)


backfill_job = backfill_graph.to_job(name="backfill_job")
