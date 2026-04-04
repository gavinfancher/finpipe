"""
Create the finpipe-dagster-sg security group.

Rules:
  - No inbound (SSM access only)
  - Outbound: HTTPS (S3, APIs, SSM, ECR), HTTP (package installs)

Usage:
    uv run python deploy/aws/ec2/dagster/sg.py
"""

from deploy.aws.config import ec2, VPC_ID, find_sg

SG_NAME = "finpipe-dagster-sg"


def create() -> str:
    """Create or find the dagster security group. Returns sg_id."""
    sg_id = find_sg(SG_NAME)

    if sg_id:
        print(f"already exists: {sg_id}")
        return sg_id

    sg = ec2.create_security_group(
        GroupName=SG_NAME,
        Description="finpipe dagster orchestrator - outbound HTTPS only, SSM access",
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

    # HTTPS — S3, AWS APIs, SSM agent, GitHub (git clone)
    ec2.authorize_security_group_egress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "tcp",
            "FromPort": 443,
            "ToPort": 443,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        }],
    )

    # HTTP — package installs
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
    print("  ingress: none (SSM only)")
    return sg_id


if __name__ == "__main__":
    create()
