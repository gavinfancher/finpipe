"""
Create the finpipe ingest ECS service.

Requires:
  - finpipe ECS cluster (deploy/aws/ecs/cluster.py)
  - finpipe-ingest task definition (deploy/aws/ecs/task.py)
  - finpipe-ecs-ingest-sg security group (deploy/aws/ecs/sg.py)

Usage:
    uv run python deploy/aws/ecs/service.py
"""

import sys

from deploy.aws.config import ecs, SUBNET_1A, SUBNET_1B, find_sg

CLUSTER_NAME = "finpipe"
SERVICE_NAME = "ingest"
TASK_FAMILY = "finpipe-ingest"
SG_NAME = "finpipe-ecs-ingest-sg"


def create() -> str:
    """Create or find the ECS service. Returns the service name."""
    sg_id = find_sg(SG_NAME)
    if not sg_id:
        print(f"error: security group {SG_NAME} not found — run ecs/sg.py first")
        sys.exit(1)

    try:
        ecs.create_service(
            cluster=CLUSTER_NAME,
            serviceName=SERVICE_NAME,
            taskDefinition=TASK_FAMILY,
            desiredCount=0,  # control node manages scaling
            capacityProviderStrategy=[
                {"capacityProvider": "FARGATE_SPOT", "weight": 1},
            ],
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": [SUBNET_1A, SUBNET_1B],
                    "securityGroups": [sg_id],
                    "assignPublicIp": "ENABLED",
                },
            },
            enableExecuteCommand=True,
            tags=[{"key": "project", "value": "finpipe"}],
        )
        print(f"created service: {SERVICE_NAME} (desiredCount=0)")
    except ecs.exceptions.ClientException as e:
        if "already exists" in str(e):
            print(f"already exists: {SERVICE_NAME}")
        else:
            raise

    print(f"  cluster: {CLUSTER_NAME}")
    print(f"  sg:      {sg_id}")
    return SERVICE_NAME


if __name__ == "__main__":
    create()
