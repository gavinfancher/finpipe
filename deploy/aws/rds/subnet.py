"""
Create the finpipe-rds-subnet DB subnet group.

Groups us-east-1a + us-east-1b subnets for RDS placement.

Usage:
    uv run python deploy/aws/rds/subnet.py
"""

from deploy.aws.config import rds, SUBNET_1A, SUBNET_1B

SUBNET_GROUP_NAME = "finpipe-rds-subnet"


def create() -> str:
    """Create or find the DB subnet group. Returns the group name."""
    try:
        rds.create_db_subnet_group(
            DBSubnetGroupName=SUBNET_GROUP_NAME,
            DBSubnetGroupDescription="finpipe RDS subnets",
            SubnetIds=[SUBNET_1A, SUBNET_1B],
        )
        print(f"created db subnet group: {SUBNET_GROUP_NAME}")
    except rds.exceptions.DBSubnetGroupAlreadyExistsFault:
        print(f"already exists: {SUBNET_GROUP_NAME}")

    return SUBNET_GROUP_NAME


if __name__ == "__main__":
    create()
