"""
Launch the finpipe-dagster 24/7 orchestrator EC2 instance.

Requires:
  - finpipe-dagster-profile instance profile (deploy/aws/ec2/dagster/iam.py)
  - finpipe-dagster-sg security group (deploy/aws/ec2/dagster/sg.py)

Usage:
    uv run python deploy/aws/ec2/dagster/instance.py
"""

import sys

from deploy.aws.config import ec2, AZ, SUBNET_1A, find_sg, get_ubuntu_ami

SG_NAME = "finpipe-dagster-sg"
PROFILE_NAME = "finpipe-dagster-profile"
INSTANCE_TYPE = "t3.small"
INSTANCE_NAME = "finpipe-dagster"


def create() -> str:
    """Launch or find the dagster instance. Returns the instance ID."""
    sg_id = find_sg(SG_NAME)
    if not sg_id:
        print(f"error: security group {SG_NAME} not found — run dagster/sg.py first")
        sys.exit(1)

    # check if already running
    existing = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": [INSTANCE_NAME]},
            {"Name": "instance-state-name", "Values": ["running", "pending"]},
        ],
    )
    existing_instances = [
        i for r in existing["Reservations"] for i in r["Instances"]
    ]

    if existing_instances:
        instance = existing_instances[0]
        instance_id = instance["InstanceId"]
        print(f"already running: {instance_id}")
    else:
        ami_id = get_ubuntu_ami()
        print(f"launching {INSTANCE_TYPE}...")
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
                    {"Key": "Name", "Value": INSTANCE_NAME},
                    {"Key": "project", "Value": "finpipe"},
                ],
            }],
            BlockDeviceMappings=[{
                "DeviceName": "/dev/sda1",
                "Ebs": {
                    "VolumeSize": 20,
                    "VolumeType": "gp3",
                    "DeleteOnTermination": True,
                },
            }],
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

    private_ip = instance.get("PrivateIpAddress", "n/a")
    state = instance["State"]["Name"]

    print()
    print(f"instance:   {instance_id}")
    print(f"state:      {state}")
    print(f"private ip: {private_ip}")
    print(f"sg:         {sg_id}")
    print()
    print(f"connect: aws ssm start-session --target {instance_id}")
    return instance_id


if __name__ == "__main__":
    create()
