"""
Launch a finpipe-backfill spot instance.

Provisions a c5n.4xlarge spot instance for high-throughput historical
data ingestion from the Massive API. Designed to be called from dagster
or run standalone.

Requires:
  - finpipe-backfill-profile instance profile (infra/ec2/backfill/iam.py)
  - finpipe-backfill-sg security group (infra/ec2/backfill/sg.py)

Usage:
    uv run python infra/ec2/backfill/instance.py
"""

import sys

from botocore.exceptions import ClientError

from infra.config import SUBNET_1A, SUBNET_1B, ec2, find_sg, get_ubuntu_ami

SG_NAME = "finpipe-backfill-sg"
PROFILE_NAME = "finpipe-backfill-profile"
INSTANCE_TYPE = "c5n.4xlarge"
INSTANCE_NAME = "finpipe-backfill"
SUBNET_FALLBACK_ORDER = [SUBNET_1A, SUBNET_1B]


def create(name_suffix: str | None = None) -> tuple[str, str]:
    """Launch a backfill spot instance. Returns (instance_id, public_ip).

    Args:
        name_suffix: Optional suffix for the instance Name tag (e.g. timestamp).
    """
    sg_id = find_sg(SG_NAME)
    if not sg_id:
        raise RuntimeError(f"security group {SG_NAME} not found — run infra/ec2/backfill/sg.py first")

    ami_id = get_ubuntu_ami()
    instance_name = f"{INSTANCE_NAME}-{name_suffix}" if name_suffix else INSTANCE_NAME

    print(f"launching {INSTANCE_TYPE} spot...")
    print(f"  ami: {ami_id}")

    resp = None
    last_error: Exception | None = None
    for subnet_id in SUBNET_FALLBACK_ORDER:
        try:
            print(f"  trying subnet: {subnet_id}")
            resp = ec2.run_instances(
                ImageId=ami_id,
                InstanceType=INSTANCE_TYPE,
                MinCount=1,
                MaxCount=1,
                IamInstanceProfile={"Name": PROFILE_NAME},
                SecurityGroupIds=[sg_id],
                SubnetId=subnet_id,
                TagSpecifications=[{
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name", "Value": instance_name},
                        {"Key": "project", "Value": "finpipe"},
                    ],
                }],
                InstanceMarketOptions={
                    "MarketType": "spot",
                    "SpotOptions": {
                        "SpotInstanceType": "one-time",
                    },
                },
                MetadataOptions={
                    "HttpTokens": "required",  # IMDSv2 only
                },
            )
            break
        except ClientError as exc:
            last_error = exc
            if exc.response.get("Error", {}).get("Code") != "InsufficientInstanceCapacity":
                raise
            print(f"  insufficient capacity in subnet {subnet_id}, trying next...")

    if resp is None:
        raise RuntimeError("no spot capacity found in configured us-east-1 subnets") from last_error
    instance = resp["Instances"][0]
    instance_id = instance["InstanceId"]
    print(f"  instance: {instance_id}")

    print("  waiting for running state...")
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance_id])

    resp = ec2.describe_instances(InstanceIds=[instance_id])
    instance = resp["Reservations"][0]["Instances"][0]
    public_ip = instance.get("PublicIpAddress", "n/a")

    print(f"  running — public ip: {public_ip}")
    return instance_id, public_ip


def terminate(instance_id: str) -> None:
    """Terminate a backfill instance."""
    ec2.terminate_instances(InstanceIds=[instance_id])
    print(f"terminated: {instance_id}")


if __name__ == "__main__":
    create()
