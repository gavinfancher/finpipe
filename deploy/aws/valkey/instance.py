"""
Provision the finpipe-cache ElastiCache Valkey replication group.

Requires:
  - finpipe-valkey-sg security group (deploy/aws/valkey/sg.py)
  - finpipe-valkey-subnet cache subnet group (deploy/aws/valkey/subnet.py)

Usage:
    uv run python deploy/aws/valkey/instance.py
"""

import sys
import time

from deploy.aws.config import elasticache, AZ, find_sg

REPL_GROUP_ID = "finpipe-cache"
SG_NAME = "finpipe-valkey-sg"
SUBNET_GROUP_NAME = "finpipe-valkey-subnet"


def create() -> str:
    """Create or find the Valkey replication group. Returns the endpoint."""
    sg_id = find_sg(SG_NAME)
    if not sg_id:
        print(f"error: security group {SG_NAME} not found — run valkey/sg.py first")
        sys.exit(1)

    try:
        elasticache.create_replication_group(
            ReplicationGroupId=REPL_GROUP_ID,
            ReplicationGroupDescription="finpipe Valkey cache",
            Engine="valkey",
            EngineVersion="8.0",
            CacheNodeType="cache.t4g.micro",
            NumCacheClusters=1,
            CacheSubnetGroupName=SUBNET_GROUP_NAME,
            SecurityGroupIds=[sg_id],
            PreferredCacheClusterAZs=[AZ],
            AutomaticFailoverEnabled=False,
            TransitEncryptionEnabled=False,
            Tags=[{"Key": "project", "Value": "finpipe"}],
        )
        print(f"creating replication group: {REPL_GROUP_ID}")
        print("this will take ~5 minutes...")
    except elasticache.exceptions.ReplicationGroupAlreadyExistsFault:
        print(f"already exists: {REPL_GROUP_ID}")

    # wait for endpoint
    print("waiting for endpoint...")
    for _ in range(40):
        resp = elasticache.describe_replication_groups(
            ReplicationGroupId=REPL_GROUP_ID,
        )
        group = resp["ReplicationGroups"][0]
        status = group["Status"]
        if status == "available":
            break
        print(f"  status: {status}")
        time.sleep(15)
    else:
        print("timed out — check: aws elasticache describe-replication-groups --replication-group-id finpipe-cache")
        sys.exit(0)

    endpoint = group["NodeGroups"][0]["PrimaryEndpoint"]["Address"]
    port = group["NodeGroups"][0]["PrimaryEndpoint"]["Port"]

    print()
    print(f"endpoint: {endpoint}")
    print(f"port:     {port}")
    print(f"sg:       {sg_id}")
    print(f"redis://{endpoint}:{port}")
    return endpoint


if __name__ == "__main__":
    create()
