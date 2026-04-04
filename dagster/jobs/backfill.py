"""
Dagster job: provision EC2 spot → SSM setup → run backfill → terminate.

No SSH keys needed. All remote commands run via SSM Run Command.
Credentials come from Secrets Manager, code from GitHub.

Usage:
    uv run dagster dev -f dagster_backfill.py
"""

import os
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

EC2_CONFIG = {
    "ImageId": "ami-0f9de6e2d2f067fca",  # Ubuntu 24.04 us-east-1
    "InstanceType": "c5n.4xlarge",
    "MinCount": 1,
    "MaxCount": 1,
    "IamInstanceProfile": {"Name": "backfill-ec2-profile"},
    "SubnetId": os.environ.get("SUBNET_1A", ""),  # us-east-1a
    "SecurityGroupIds": [os.environ.get("BACKFILL_SG_ID", "")],
    "TagSpecifications": [{
        "ResourceType": "instance",
        "Tags": [{"Key": "Name", "Value": "finpipe-backfill"}],
    }],
}

REPO_URL = "https://github.com/gavinfancher/massive-ingestion.git"
REGION = "us-east-1"


class BackfillConfig(Config):
    year: int = 2025
    months: list[int] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    workers: int = 16


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

        # stream new output since last poll
        if log_fn:
            stdout = result.get("StandardOutputContent", "")
            stderr = result.get("StandardErrorContent", "")

            if len(stdout) > last_stdout_len:
                new_lines = stdout[last_stdout_len:].strip().split("\n")
                for line in new_lines:
                    if line.strip():
                        log_fn("info", line)
                last_stdout_len = len(stdout)

            if len(stderr) > last_stderr_len:
                new_lines = stderr[last_stderr_len:].strip().split("\n")
                for line in new_lines:
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


def _terminate(instance_id):
    """Terminate an EC2 instance."""
    ec2 = boto3.client("ec2", region_name=REGION)
    ec2.terminate_instances(InstanceIds=[instance_id])


# ---------- ops ----------


@op(
    out={"instance_id": Out(str)}
)
def launch_instance():
    """Launch EC2 spot instance."""
    log = get_dagster_logger()
    ec2 = boto3.client("ec2", region_name=REGION)

    config = {**EC2_CONFIG}
    ts = pendulum.now().format("YYYY-MM-DD-HH-mm")
    config["TagSpecifications"] = [{
        "ResourceType": "instance",
        "Tags": [{"Key": "Name", "Value": f"finpipe-backfill-{ts}"}],
    }]

    log.info(f"launching {config['InstanceType']} spot in us-east-1a...")
    resp = ec2.run_instances(**config)
    instance_id = resp["Instances"][0]["InstanceId"]
    log.info(f"instance id: {instance_id}")

    log.info("waiting for running state...")
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance_id])
    log.info(f"{instance_id} is running")

    return instance_id


@op(
    out={"ssm_ready": Out(Nothing)}
)
def wait_for_ssm_agent(instance_id: str):
    """Wait for the SSM agent to register and come online."""
    log = get_dagster_logger()
    log.info(f"waiting for SSM agent on {instance_id}...")

    start = time.monotonic()
    wait_for_ssm(instance_id, timeout=300)
    log.info(f"SSM agent online ({time.monotonic() - start:.0f}s)")


@op(
    ins={"ssm_ready": In(Nothing)},
    out={"code_ready": Out(Nothing)}
)
def pull_code(instance_id: str):
    """Clone repo and install dependencies via SSM."""
    log = get_dagster_logger()

    def log_fn(level, msg):
        getattr(log, level)(msg)

    log.info(f"cloning {REPO_URL}")
    status, stdout, stderr = ssm_run(instance_id, [
        f"git clone {REPO_URL} /home/ubuntu/massive-ingestion",
    ], log_fn=log_fn)
    if status != "Success":
        raise RuntimeError(f"git clone failed: {stderr}")
    log.info("repo cloned")

    log.info("installing uv and dependencies")
    status, stdout, stderr = ssm_run(instance_id, [
        "curl -LsSf https://astral.sh/uv/install.sh | sh",
        "cd /home/ubuntu/massive-ingestion && /root/.local/bin/uv sync",
    ], timeout=120, log_fn=log_fn)
    if status != "Success":
        raise RuntimeError(f"dependency install failed: {stderr}")
    log.info("dependencies installed")



# ---------- job ----------


@op(ins={"code_ready": In(Nothing)}, out=Out(str))
def run_backfill_safe(config: BackfillConfig, instance_id: str) -> str:
    """Run backfill in background, tail log file for live output."""
    log = get_dagster_logger()
    ssm = boto3.client("ssm", region_name=REGION)
    months_str = " ".join(str(m) for m in config.months)
    log_file = "/tmp/backfill.log"
    pid_file = "/tmp/backfill.pid"

    log.info(f"starting backfill: year={config.year} months={months_str} workers={config.workers}")

    try:
        # launch backfill in background, write output to log file
        cmd = (
            f"cd /home/ubuntu/massive-ingestion && /root/.local/bin/uv run main.py"
            f" --year {config.year}"
            f" --months {months_str}"
            f" --mode concurrent"
            f" --workers {config.workers}"
            f" > {log_file} 2>&1 & echo $! > {pid_file}"
        )
        status, _, stderr = ssm_run(instance_id, [cmd])
        if status != "Success":
            log.error(f"failed to launch backfill: {stderr}")
            return "failed"

        # poll the log file for new output
        last_line_count = 0
        while True:
            time.sleep(10)

            # check if process is still running
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
                    # get exit code
                    _, exit_out, _ = ssm_run(instance_id, [
                        f"wait $(cat {pid_file}) 2>/dev/null; cat {pid_file} | xargs -I{{}} sh -c 'wait {{}} 2>/dev/null; echo $?'"
                    ])
                    log.info("backfill process finished")
                    # grab any remaining output
                    _, final_out, _ = ssm_run(instance_id, [
                        f"tail -n +{last_line_count + 1} {log_file}",
                    ])
                    if final_out and final_out.strip():
                        for line in final_out.strip().split("\n"):
                            if line.strip():
                                log.info(line)

                    return "success"

        return "success"

    except Exception as e:
        log.error(f"backfill error: {e}")
        return "failed"


@op
def terminate_and_report(instance_id: str, backfill_result: str):
    """Terminate the instance. Always runs regardless of backfill outcome."""
    log = get_dagster_logger()

    log.info(f"terminating {instance_id}...")
    _terminate(instance_id)
    log.info(f"{instance_id} terminated")

    if backfill_result != "success":
        raise RuntimeError("backfill did not succeed — instance terminated, check logs above")


@graph
def backfill_graph():
    instance_id = launch_instance()
    ssm_ready = wait_for_ssm_agent(instance_id=instance_id)
    code_ready = pull_code(instance_id=instance_id, ssm_ready=ssm_ready)
    backfill_result = run_backfill_safe(instance_id=instance_id, code_ready=code_ready)
    terminate_and_report(instance_id=instance_id, backfill_result=backfill_result)


backfill_job = backfill_graph.to_job(name="backfill_job")
