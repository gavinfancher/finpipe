"""
Create the finpipe-emr-role for EMR Serverless jobs.

Policies:
  - S3 read/write on finpipe-lakehouse bucket
  - Glue catalog access (databases, tables)

Usage:
    uv run python infra/emr/iam.py
"""

import json

from infra.config import iam, REGION, ACCOUNT_ID

ROLE_NAME = "finpipe-emr-role"
BUCKET = "finpipe-lakehouse"


def create() -> str:
    """Create or find the EMR Serverless execution role. Returns the role ARN."""

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "emr-serverless.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    }

    try:
        resp = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Tags=[{"Key": "project", "Value": "finpipe"}],
        )
        role_arn = resp["Role"]["Arn"]
        print(f"created role: {ROLE_NAME}")
    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{ROLE_NAME}"
        print(f"already exists: {ROLE_NAME}")

    # S3 — read/write lakehouse bucket
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="s3-lakehouse",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:ListBucket",
                ],
                "Resource": [
                    f"arn:aws:s3:::{BUCKET}",
                    f"arn:aws:s3:::{BUCKET}/*",
                ],
            }],
        }),
    )

    # Glue — catalog operations for Iceberg tables
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="glue-catalog",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": [
                    "glue:GetDatabase",
                    "glue:GetDatabases",
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:CreateTable",
                    "glue:UpdateTable",
                    "glue:DeleteTable",
                    "glue:GetPartitions",
                ],
                "Resource": [
                    f"arn:aws:glue:{REGION}:{ACCOUNT_ID}:catalog",
                    f"arn:aws:glue:{REGION}:{ACCOUNT_ID}:database/finpipe_*",
                    f"arn:aws:glue:{REGION}:{ACCOUNT_ID}:table/finpipe_*/*",
                ],
            }],
        }),
    )

    print(f"  policies: s3-lakehouse, glue-catalog")
    print(f"  arn: {role_arn}")
    return role_arn


if __name__ == "__main__":
    create()
