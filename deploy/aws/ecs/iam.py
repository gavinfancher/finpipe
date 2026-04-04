"""
Create IAM roles for ECS Fargate ingest tasks.

  - finpipe-ecs-execution-role: image pulls, CloudWatch logs, secrets
  - finpipe-ecs-task-role: runtime permissions (none needed currently)

Usage:
    uv run python deploy/aws/ecs/iam.py
"""

import json

from deploy.aws.config import iam, REGION, ACCOUNT_ID

EXECUTION_ROLE = "finpipe-ecs-execution-role"
TASK_ROLE = "finpipe-ecs-task-role"


def create() -> tuple[str, str]:
    """Create or find both ECS IAM roles. Returns (execution_role_arn, task_role_arn)."""

    ecs_trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "ecs-tasks.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    }

    # --- execution role ---

    try:
        iam.create_role(
            RoleName=EXECUTION_ROLE,
            AssumeRolePolicyDocument=json.dumps(ecs_trust),
            Tags=[{"Key": "project", "Value": "finpipe"}],
        )
        print(f"created execution role: {EXECUTION_ROLE}")
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"already exists: {EXECUTION_ROLE}")

    iam.attach_role_policy(
        RoleName=EXECUTION_ROLE,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
    )

    iam.put_role_policy(
        RoleName=EXECUTION_ROLE,
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
    print("  policies: ecs-execution, secrets")

    # --- task role ---

    try:
        iam.create_role(
            RoleName=TASK_ROLE,
            AssumeRolePolicyDocument=json.dumps(ecs_trust),
            Tags=[{"Key": "project", "Value": "finpipe"}],
        )
        print(f"created task role: {TASK_ROLE}")
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"already exists: {TASK_ROLE}")

    print("  task role: no extra policies needed")

    execution_role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{EXECUTION_ROLE}"
    task_role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{TASK_ROLE}"
    return execution_role_arn, task_role_arn


if __name__ == "__main__":
    create()
