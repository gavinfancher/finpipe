"""
Register the finpipe-ingest ECS task definition.

Requires:
  - finpipe-ecs-execution-role (deploy/aws/ecs/iam.py)
  - finpipe-ecs-task-role (deploy/aws/ecs/iam.py)
  - /ecs/finpipe-ingest log group (deploy/aws/ecs/logs.py)

Usage:
    uv run python deploy/aws/ecs/task.py
"""

from deploy.aws.config import ecs, REGION, ACCOUNT_ID

TASK_FAMILY = "finpipe-ingest"
LOG_GROUP = "/ecs/finpipe-ingest"
EXECUTION_ROLE = "finpipe-ecs-execution-role"
TASK_ROLE = "finpipe-ecs-task-role"
INGEST_IMAGE = f"{ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com/finpipe-backend:latest"


def create() -> str:
    """Register the task definition. Returns the task family."""
    execution_role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{EXECUTION_ROLE}"
    task_role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{TASK_ROLE}"

    ecs.register_task_definition(
        family=TASK_FAMILY,
        networkMode="awsvpc",
        requiresCompatibilities=["FARGATE"],
        cpu="256",       # 0.25 vCPU
        memory="512",    # 0.5 GB
        executionRoleArn=execution_role_arn,
        taskRoleArn=task_role_arn,
        containerDefinitions=[{
            "name": "ingest",
            "image": INGEST_IMAGE,
            "command": ["uv", "run", "python", "-m", "streaming.ingest"],
            "essential": True,
            "environment": [
                {"name": "KAFKA_BOOTSTRAP", "value": "PLACEHOLDER_REDPANDA_IP:9092"},
                {"name": "REDIS_URL", "value": "redis://PLACEHOLDER_VALKEY_ENDPOINT:6379"},
                {"name": "CONTROL_URL", "value": "http://PLACEHOLDER_EC2_PRIVATE_IP:8081"},
            ],
            "secrets": [
                {
                    "name": "MASSIVE_API_KEY",
                    "valueFrom": f"arn:aws:secretsmanager:{REGION}:{ACCOUNT_ID}:secret:finpipe/massive-api-key",
                },
            ],
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group": LOG_GROUP,
                    "awslogs-region": REGION,
                    "awslogs-stream-prefix": "ingest",
                },
            },
        }],
        tags=[{"key": "project", "value": "finpipe"}],
    )
    print(f"registered task definition: {TASK_FAMILY}")
    print(f"  image: {INGEST_IMAGE}")
    print(f"  cpu: 0.25 vCPU, memory: 0.5 GB")
    return TASK_FAMILY


if __name__ == "__main__":
    create()
