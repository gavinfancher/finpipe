"""
Create the finpipe-ec2-role IAM role and instance profile.

Policies:
  - Secrets Manager (pull .env + tunnel token)
  - RDS describe (resolve endpoint in user-data)
  - ECS scaling (control node scales ingest service)
  - ECR pull (docker pull backend image)
  - SSM (remote shell access, no SSH needed)

Usage:
    uv run python deploy/aws/ec2/control/iam.py
"""

import json
import time

from deploy.aws.config import iam, REGION, ACCOUNT_ID

ROLE_NAME = "finpipe-ec2-role"
PROFILE_NAME = "finpipe-ec2-profile"


def create() -> str:
    """Create or find the IAM role and instance profile. Returns the profile name."""

    # --- role ---

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

    # secrets manager
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

    # rds describe — user-data resolves endpoint dynamically
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="rds-describe",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": "rds:DescribeDBInstances",
                "Resource": f"arn:aws:rds:{REGION}:{ACCOUNT_ID}:db:finpipe-db",
            }],
        }),
    )

    # elasticache describe — user-data resolves valkey endpoint dynamically
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="elasticache-describe",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": "elasticache:DescribeReplicationGroups",
                "Resource": f"arn:aws:elasticache:{REGION}:{ACCOUNT_ID}:replicationgroup:finpipe-cache",
            }],
        }),
    )

    # ecs scaling
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="ecs-ingest-scaling",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": [
                    "ecs:DescribeServices",
                    "ecs:UpdateService",
                ],
                "Resource": f"arn:aws:ecs:{REGION}:{ACCOUNT_ID}:service/finpipe/ingest",
            }],
        }),
    )

    # ecr pull
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="ecr-pull",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "ecr:GetDownloadUrlForLayer",
                        "ecr:BatchGetImage",
                        "ecr:BatchCheckLayerAvailability",
                    ],
                    "Resource": f"arn:aws:ecr:{REGION}:{ACCOUNT_ID}:repository/finpipe-backend",
                },
                {
                    "Effect": "Allow",
                    "Action": "ecr:GetAuthorizationToken",
                    "Resource": "*",
                },
            ],
        }),
    )

    # ssm
    iam.attach_role_policy(
        RoleName=ROLE_NAME,
        PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
    )

    print("  policies: secrets, rds, ecs, ecr, ssm")

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
