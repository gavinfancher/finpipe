"""
Create the finpipe-backfill-role IAM role and instance profile.

Policies:
  - S3 read/write (staged parquet to finpipe-root bucket)
  - Secrets Manager (Massive API key)
  - SSM (remote commands, no SSH needed)

Usage:
    uv run python deploy/aws/ec2/backfill/iam.py
"""

import json
import time

from deploy.aws.config import iam, REGION, ACCOUNT_ID

ROLE_NAME = "finpipe-backfill-role"
PROFILE_NAME = "finpipe-backfill-profile"
BUCKET = "finpipe-root"


def create() -> str:
    """Create or find the backfill IAM role and instance profile. Returns the profile name."""

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

    # S3 — read/write staged parquet files
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

    # Secrets Manager — Massive API key
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

    # SSM — remote shell access (no SSH needed)
    iam.attach_role_policy(
        RoleName=ROLE_NAME,
        PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
    )

    print("  policies: s3, secrets, ssm")

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
