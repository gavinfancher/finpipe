"""
Create the finpipe-ecs-ingest-sg security group.

Rules:
  - No inbound
  - Outbound: 443 (Massive API + ECR), 9092 + 8081 → EC2 control, 6379 → Valkey

Cross-links to finpipe-ec2-sg and finpipe-valkey-sg when they exist.

Usage:
    uv run python deploy/aws/ecs/sg.py
"""

from deploy.aws.config import ec2, VPC_ID, find_sg

SG_NAME = "finpipe-ecs-ingest-sg"


def create() -> str:
    """Create or find the ECS ingest security group. Returns sg_id."""
    sg_id = find_sg(SG_NAME)

    if sg_id:
        print(f"already exists: {sg_id}")
        return sg_id

    sg = ec2.create_security_group(
        GroupName=SG_NAME,
        Description="finpipe ECS ingest tasks - restricted outbound",
        VpcId=VPC_ID,
        TagSpecifications=[{
            "ResourceType": "security-group",
            "Tags": [{"Key": "project", "Value": "finpipe"}],
        }],
    )
    sg_id = sg["GroupId"]
    print(f"created: {sg_id}")

    # replace default allow-all outbound
    ec2.revoke_security_group_egress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "-1",
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        }],
    )

    # HTTPS — Massive API, ECR image pulls, AWS APIs
    ec2.authorize_security_group_egress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "tcp",
            "FromPort": 443,
            "ToPort": 443,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        }],
    )
    print("  egress: 443 → internet (Massive API, ECR)")

    # Redpanda + control API → EC2 control node
    ec2_sg_id = find_sg("finpipe-ec2-sg")
    if ec2_sg_id:
        for port, label in [(9092, "Redpanda"), (8081, "control API")]:
            ec2.authorize_security_group_egress(
                GroupId=sg_id,
                IpPermissions=[{
                    "IpProtocol": "tcp",
                    "FromPort": port,
                    "ToPort": port,
                    "UserIdGroupPairs": [{"GroupId": ec2_sg_id}],
                }],
            )
            print(f"  egress: {port} → EC2 control ({label})")
    else:
        print("  warning: finpipe-ec2-sg not found, skipping EC2 egress")

    # Redis → Valkey
    valkey_sg_id = find_sg("finpipe-valkey-sg")
    if valkey_sg_id:
        ec2.authorize_security_group_egress(
            GroupId=sg_id,
            IpPermissions=[{
                "IpProtocol": "tcp",
                "FromPort": 6379,
                "ToPort": 6379,
                "UserIdGroupPairs": [{"GroupId": valkey_sg_id}],
            }],
        )
        # add ingress on valkey SG for ECS tasks
        try:
            ec2.authorize_security_group_ingress(
                GroupId=valkey_sg_id,
                IpPermissions=[{
                    "IpProtocol": "tcp",
                    "FromPort": 6379,
                    "ToPort": 6379,
                    "UserIdGroupPairs": [{"GroupId": sg_id}],
                }],
            )
        except Exception as e:
            if "already exists" not in str(e):
                raise
        print(f"  egress: 6379 → Valkey ({valkey_sg_id})")
    else:
        print("  warning: finpipe-valkey-sg not found, skipping Valkey egress")

    return sg_id


if __name__ == "__main__":
    create()
