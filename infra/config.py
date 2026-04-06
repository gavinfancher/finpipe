"""
Shared configuration for all AWS provisioning scripts.

Provides region, VPC/subnet IDs, account ID, boto3 clients, and
common helpers. Every script under infra/ imports from here
instead of duplicating setup.
"""

import boto3

# ---------- region / account ----------

REGION = "us-east-1"
AZ = "us-east-1a"
ACCOUNT_ID = "809000566572"


# ---------- networking ----------

VPC_ID = "vpc-0d17c300bee12bf9f"
SUBNET_1A = "subnet-074afec090850ea1a"  # us-east-1a
SUBNET_1B = "subnet-097b8d2beacf96f1b"  # us-east-1b


# ---------- boto3 clients ----------

ec2 = boto3.client("ec2", region_name=REGION)
iam = boto3.client("iam")
rds = boto3.client("rds", region_name=REGION)
elasticache = boto3.client("elasticache", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)


# ---------- helpers ----------

def find_sg(name: str, vpc_id: str | None = None) -> str | None:
    """Look up a security group ID by name within the project VPC."""
    vpc = vpc_id or VPC_ID
    resp = ec2.describe_security_groups(
        Filters=[
            {"Name": "group-name", "Values": [name]},
            {"Name": "vpc-id", "Values": [vpc]},
        ],
    )
    groups = resp["SecurityGroups"]
    return groups[0]["GroupId"] if groups else None


def get_ubuntu_ami() -> str:
    """Get the latest Ubuntu 24.04 LTS AMI for the configured region."""
    resp = ssm.get_parameter(
        Name="/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
    )
    return resp["Parameter"]["Value"]
