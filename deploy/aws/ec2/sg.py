"""
Create the finpipe-ec2-sg security group.

Rules:
  - No inbound (zero attack surface) except from ECS ingest (9092, 8081)
  - Outbound: HTTPS, HTTP, RDS (5432), Valkey (6379)

Cross-links to finpipe-rds-sg, finpipe-valkey-sg, and finpipe-ecs-ingest-sg
when they exist.

Usage:
    uv run python deploy/aws/ec2/sg.py
"""

from deploy.aws.config import ec2, VPC_ID, find_sg

SG_NAME = "finpipe-ec2-sg"


def create() -> str:
    """Create or find the EC2 security group. Returns sg_id."""
    sg_id = find_sg(SG_NAME)

    if sg_id:
        print(f"already exists: {sg_id}")
        return sg_id

    sg = ec2.create_security_group(
        GroupName=SG_NAME,
        Description="finpipe EC2 core - no inbound, outbound to managed services",
        VpcId=VPC_ID,
        TagSpecifications=[{
            "ResourceType": "security-group",
            "Tags": [{"Key": "project", "Value": "finpipe"}],
        }],
    )
    sg_id = sg["GroupId"]
    print(f"created: {sg_id}")

    # replace default allow-all outbound with explicit rules
    ec2.revoke_security_group_egress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "-1",
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        }],
    )

    # HTTPS — cloudflared tunnel, docker pulls, SSM, AWS APIs
    ec2.authorize_security_group_egress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "tcp",
            "FromPort": 443,
            "ToPort": 443,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        }],
    )

    # HTTP — package installs during bootstrap
    ec2.authorize_security_group_egress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "tcp",
            "FromPort": 80,
            "ToPort": 80,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        }],
    )
    print("  egress: 443, 80 → internet")

    # Postgres → RDS security group
    rds_sg_id = find_sg("finpipe-rds-sg")
    if rds_sg_id:
        ec2.authorize_security_group_egress(
            GroupId=sg_id,
            IpPermissions=[{
                "IpProtocol": "tcp",
                "FromPort": 5432,
                "ToPort": 5432,
                "UserIdGroupPairs": [{"GroupId": rds_sg_id}],
            }],
        )
        # allow RDS to accept connections from this EC2
        try:
            ec2.authorize_security_group_ingress(
                GroupId=rds_sg_id,
                IpPermissions=[{
                    "IpProtocol": "tcp",
                    "FromPort": 5432,
                    "ToPort": 5432,
                    "UserIdGroupPairs": [{"GroupId": sg_id}],
                }],
            )
        except Exception as e:
            if "already exists" not in str(e):
                raise
        print(f"  egress: 5432 → RDS ({rds_sg_id})")
    else:
        print("  warning: finpipe-rds-sg not found, skipping RDS egress")

    # Redis → Valkey security group
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

    # Inbound from ECS ingest tasks (9092 Redpanda, 8081 control API)
    ecs_sg_id = find_sg("finpipe-ecs-ingest-sg")
    if ecs_sg_id:
        for port, label in [(9092, "Redpanda"), (8081, "control API")]:
            try:
                ec2.authorize_security_group_ingress(
                    GroupId=sg_id,
                    IpPermissions=[{
                        "IpProtocol": "tcp",
                        "FromPort": port,
                        "ToPort": port,
                        "UserIdGroupPairs": [{"GroupId": ecs_sg_id}],
                    }],
                )
            except Exception as e:
                if "already exists" not in str(e):
                    raise
            print(f"  ingress: {port} ← ECS ingest ({label})")
    else:
        print("  warning: finpipe-ecs-ingest-sg not found, skipping ECS inbound")

    return sg_id


if __name__ == "__main__":
    create()
