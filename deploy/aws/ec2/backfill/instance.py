"""
Launch a finpipe-backfill spot instance.

Provisions a c5n.4xlarge spot instance for high-throughput historical
data ingestion from the Massive API. Designed to be called from dagster
or run standalone.

Requires:
  - finpipe-backfill-profile instance profile (deploy/aws/ec2/backfill/iam.py)
  - finpipe-backfill-sg security group (deploy/aws/ec2/backfill/sg.py)

Usage:
    uv run python deploy/aws/ec2/backfill/instance.py
"""

import sys

from deploy.aws.config import ec2, SUBNET_1A, find_sg, get_ubuntu_ami

SG_NAME = "finpipe-backfill-sg"
PROFILE_NAME = "finpipe-backfill-profile"
INSTANCE_TYPE = "c5n.4xlarge"
INSTANCE_NAME = "finpipe-backfill"


def create(name_suffix: str | None = None) -> tuple[str, str]:
    """Launch a backfill spot instance. Returns (instance_id, public_ip).

    Args:
        name_suffix: Optional suffix for the instance Name tag (e.g. timestamp).
    """
    sg_id = find_sg(SG_NAME)
    if not sg_id:
        print(f"error: security group {SG_NAME} not found — run backfill/sg.py first")
        sys.exit(1)

    ami_id = get_ubuntu_ami()
    instance_name = f"{INSTANCE_NAME}-{name_suffix}" if name_suffix else INSTANCE_NAME

    print(f"launching {INSTANCE_TYPE} spot...")
    print(f"  ami: {ami_id}")

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
            "SpotOptions": {
                "SpotInstanceType": "one-time",
            },
        },
        MetadataOptions={
            "HttpTokens": "required",  # IMDSv2 only
        },
    )
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
