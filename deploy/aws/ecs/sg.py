"""
Create the finpipe-ecs-ingest-sg security group.

ECS ingest tasks need outbound only:
  - 443: Massive API
  - 9092: EC2 Redpanda
  - 6379: ElastiCache Valkey

Usage:
    uv run python deploy/aws/ecs/sg.py
"""

from deploy.aws.config import ec2, VPC_ID

SG_NAME = "finpipe-ecs-ingest-sg"


def create() -> str:
    """Create or find the ECS ingest security group. Returns sg_id."""
    try:
        sg = ec2.create_security_group(
            GroupName=SG_NAME,
            Description="finpipe ECS ingest tasks - outbound only",
            VpcId=VPC_ID,
            TagSpecifications=[{
                "ResourceType": "security-group",
                "Tags": [{"Key": "project", "Value": "finpipe"}],
            }],
        )
        sg_id = sg["GroupId"]
        print(f"created security group: {sg_id}")
        return sg_id

    except Exception as e:
        if "already exists" in str(e):
            sgs = ec2.describe_security_groups(
                Filters=[{"Name": "group-name", "Values": [SG_NAME]}],
            )
            sg_id = sgs["SecurityGroups"][0]["GroupId"]
            print(f"already exists: {sg_id}")
            return sg_id
        raise


if __name__ == "__main__":
    create()
