"""
Launch a finpipe-ingest spot instance for daily file ingestion.

Small instance for downloading daily .csv.gz files from Massive S3,
converting to parquet with PyArrow, and staging to S3. Terminated
after the job completes.

Requires:
  - finpipe-backfill-profile instance profile (infra/ec2/backfill/iam.py)
  - finpipe-backfill-sg security group (infra/ec2/backfill/sg.py)

Reuses backfill IAM/SG since the permissions are identical (S3 write, Secrets, SSM).

Usage:
    uv run python infra/ec2/ingest/instance.py
"""

import sys

from infra.config import ec2, SUBNET_1A, find_sg, get_ubuntu_ami

SG_NAME = "finpipe-backfill-sg"
PROFILE_NAME = "finpipe-backfill-profile"
INSTANCE_TYPE = "t3.small"
INSTANCE_NAME = "finpipe-ingest"


def create(name_suffix: str | None = None) -> tuple[str, str]:
    """Launch an ingest spot instance. Returns (instance_id, public_ip)."""
    sg_id = find_sg(SG_NAME)
    if not sg_id:
        print(f"error: security group {SG_NAME} not found — run infra/ec2/backfill/sg.py first")
        sys.exit(1)

    ami_id = get_ubuntu_ami()
    instance_name = f"{INSTANCE_NAME}-{name_suffix}" if name_suffix else INSTANCE_NAME

    print(f"launching {INSTANCE_TYPE} spot...")

    resp = ec2.run_instances(
        ImageId=ami_id,
        InstanceType=INSTANCE_TYPE,
        MinCount=1,
        MaxCount=1,
        IamInstanceProfile={"Name": PROFILE_NAME},
        SecurityGroupIds=[sg_id],
        SubnetId=SUBNET_1A,
        TagSpecifications=[{
            "ResourceType": "instance",
            "Tags": [
                {"Key": "Name", "Value": instance_name},
                {"Key": "project", "Value": "finpipe"},
            ],
        }],
        InstanceMarketOptions={
            "MarketType": "spot",
            "SpotOptions": {"SpotInstanceType": "one-time"},
        },
        MetadataOptions={"HttpTokens": "required"},
    )
    instance = resp["Instances"][0]
    instance_id = instance["InstanceId"]

    print(f"  waiting for running state...")
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance_id])

    resp = ec2.describe_instances(InstanceIds=[instance_id])
    instance = resp["Reservations"][0]["Instances"][0]
    public_ip = instance.get("PublicIpAddress", "n/a")

    print(f"  running — {instance_id} ({public_ip})")
    return instance_id, public_ip


def terminate(instance_id: str) -> None:
    """Terminate an ingest instance."""
    ec2.terminate_instances(InstanceIds=[instance_id])
    print(f"terminated: {instance_id}")


if __name__ == "__main__":
    create()
