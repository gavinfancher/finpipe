"""
Create the finpipe-dagster-role IAM role and instance profile.

Policies:
  - EC2 (provision/terminate backfill spot instances)
  - IAM PassRole (assign backfill instance profile)
  - S3 read/write (finpipe-root bucket)
  - Secrets Manager (API keys)
  - SSM (run commands on backfill instances)

Usage:
    uv run python deploy/aws/ec2/dagster/iam.py
"""

import json
import time

from deploy.aws.config import iam, REGION, ACCOUNT_ID

ROLE_NAME = "finpipe-dagster-role"
PROFILE_NAME = "finpipe-dagster-profile"
BUCKET = "finpipe-root"


def create() -> str:
    """Create or find the dagster IAM role and instance profile. Returns the profile name."""

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "ec2.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    }

    try:
        iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Tags=[{"Key": "project", "Value": "finpipe"}],
        )
        print(f"created role: {ROLE_NAME}")
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"already exists: {ROLE_NAME}")

    # EC2 — provision and terminate backfill spot instances
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="ec2-backfill-management",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": [
                    "ec2:RunInstances",
                    "ec2:TerminateInstances",
                    "ec2:DescribeInstances",
                    "ec2:DescribeInstanceStatus",
                    "ec2:CreateTags",
                ],
                "Resource": "*",
                "Condition": {
                    "StringEquals": {"aws:RequestedRegion": REGION},
                },
            }],
        }),
    )

    # IAM PassRole — allow assigning backfill instance profile
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="iam-passrole-backfill",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": "iam:PassRole",
                "Resource": f"arn:aws:iam::{ACCOUNT_ID}:role/finpipe-backfill-role",
            }],
        }),
    )

    # S3 — read/write for orchestration data
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="s3-access",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                "Resource": [
                    f"arn:aws:s3:::{BUCKET}",
                    f"arn:aws:s3:::{BUCKET}/*",
                ],
            }],
        }),
    )

    # Secrets Manager
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="secrets-access",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": "secretsmanager:GetSecretValue",
                "Resource": f"arn:aws:secretsmanager:{REGION}:{ACCOUNT_ID}:secret:finpipe/*",
            }],
        }),
    )

    # SSM — run commands on backfill instances
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="ssm-command",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": [
                    "ssm:SendCommand",
                    "ssm:GetCommandInvocation",
                    "ssm:DescribeInstanceInformation",
                ],
                "Resource": "*",
            }],
        }),
    )

    # SSM agent for the dagster instance itself
    iam.attach_role_policy(
        RoleName=ROLE_NAME,
        PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
    )

    print("  policies: ec2, passrole, s3, secrets, ssm")

    # --- instance profile ---

    try:
        iam.create_instance_profile(InstanceProfileName=PROFILE_NAME)
        iam.add_role_to_instance_profile(
            InstanceProfileName=PROFILE_NAME,
            RoleName=ROLE_NAME,
        )
        print(f"created instance profile: {PROFILE_NAME}")
        print("  waiting for IAM propagation...")
        time.sleep(10)
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"instance profile already exists: {PROFILE_NAME}")

    return PROFILE_NAME


if __name__ == "__main__":
    create()
