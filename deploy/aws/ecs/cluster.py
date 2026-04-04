"""
Create the finpipe ECS cluster with Fargate Spot capacity.

Usage:
    uv run python deploy/aws/ecs/cluster.py
"""

from deploy.aws.config import ecs

CLUSTER_NAME = "finpipe"


def create() -> str:
    """Create or find the ECS cluster. Returns the cluster name."""
    existing = ecs.describe_clusters(clusters=[CLUSTER_NAME])
    active = [c for c in existing["clusters"] if c["status"] == "ACTIVE"]

    if active:
        print(f"already exists: {CLUSTER_NAME}")
    else:
        ecs.create_cluster(
            clusterName=CLUSTER_NAME,
            capacityProviders=["FARGATE_SPOT", "FARGATE"],
            defaultCapacityProviderStrategy=[
                {"capacityProvider": "FARGATE_SPOT", "weight": 1},
            ],
            tags=[{"key": "project", "value": "finpipe"}],
        )
        print(f"created cluster: {CLUSTER_NAME}")

    return CLUSTER_NAME


if __name__ == "__main__":
    create()
