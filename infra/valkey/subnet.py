"""
Create the finpipe-valkey-subnet cache subnet group.

Groups us-east-1a + us-east-1b subnets for ElastiCache placement.

Usage:
    uv run python infra/valkey/subnet.py
"""

from infra.config import elasticache, SUBNET_1A, SUBNET_1B

SUBNET_GROUP_NAME = "finpipe-valkey-subnet"


def create() -> str:
    """Create or find the cache subnet group. Returns the group name."""
    try:
        elasticache.create_cache_subnet_group(
            CacheSubnetGroupName=SUBNET_GROUP_NAME,
            CacheSubnetGroupDescription="finpipe Valkey subnets",
            SubnetIds=[SUBNET_1A, SUBNET_1B],
        )
        print(f"created subnet group: {SUBNET_GROUP_NAME}")
    except elasticache.exceptions.CacheSubnetGroupAlreadyExistsFault:
        print(f"already exists: {SUBNET_GROUP_NAME}")

    return SUBNET_GROUP_NAME


if __name__ == "__main__":
    create()
