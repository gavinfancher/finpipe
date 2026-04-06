"""
Launch the finpipe-streaming EC2 instance (control node).

Requires:
  - finpipe-ec2-profile instance profile (infra/ec2/control/iam.py)
  - finpipe-ec2-sg security group (infra/ec2/control/sg.py)

Usage:
    uv run python infra/ec2/control/instance.py
"""

import os
import sys

from infra.config import ec2, AZ, SUBNET_1A, find_sg, get_ubuntu_ami

SG_NAME = "finpipe-ec2-sg"
PROFILE_NAME = "finpipe-ec2-profile"
KEY_NAME = "macbook-pro-key"
INSTANCE_TYPE = "t3.medium"
INSTANCE_NAME = "finpipe-streaming"


def create() -> str:
    """Launch or find the EC2 instance. Returns the instance ID."""
    sg_id = find_sg(SG_NAME)
    if not sg_id:
        print(f"error: security group {SG_NAME} not found — run ec2/control/sg.py first")
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
        print(f"ami: {ami_id} (Ubuntu 24.04 LTS)")

        # read user-data bootstrap script
        ec2_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "ec2")
        with open(os.path.join(ec2_dir, "user-data.sh")) as f:
            user_data = f.read()

        resp = ec2.run_instances(
            ImageId=ami_id,
            InstanceType=INSTANCE_TYPE,
            MinCount=1,
            MaxCount=1,
            KeyName=KEY_NAME,
            IamInstanceProfile={"Name": PROFILE_NAME},
            SecurityGroupIds=[sg_id],
            SubnetId=SUBNET_1A,
            UserData=user_data,
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
        print(f"launched: {instance_id} ({INSTANCE_TYPE}, {AZ})")
        print("waiting for running state...")

        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[instance_id])

        resp = ec2.describe_instances(InstanceIds=[instance_id])
        instance = resp["Reservations"][0]["Instances"][0]

    private_ip = instance.get("PrivateIpAddress", "n/a")
    public_ip = instance.get("PublicIpAddress", "n/a")
    state = instance["State"]["Name"]

    print()
    print(f"instance:   {instance_id}")
    print(f"state:      {state}")
    print(f"private ip: {private_ip}")
    print(f"public ip:  {public_ip}")
    print(f"sg:         {sg_id}")
    print()
    print(f"ssh: ssh -i ~/.ssh/macbook-pro-key ubuntu@{public_ip}")
    print(f"ssm: aws ssm start-session --target {instance_id}")
    return instance_id


if __name__ == "__main__":
    create()
