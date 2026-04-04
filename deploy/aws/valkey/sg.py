"""
Create the finpipe-valkey-sg security group.

Allows inbound Redis/Valkey (6379) from within the VPC.

Usage:
    uv run python deploy/aws/valkey/sg.py
"""

from deploy.aws.config import ec2, VPC_ID

SG_NAME = "finpipe-valkey-sg"


def create() -> str:
    """Create or find the Valkey security group. Returns sg_id."""
    try:
        sg = ec2.create_security_group(
            GroupName=SG_NAME,
            Description="Valkey access from within VPC only",
            VpcId=VPC_ID,
            TagSpecifications=[{
                "ResourceType": "security-group",
                "Tags": [{"Key": "project", "Value": "finpipe"}],
            }],
        )
        sg_id = sg["GroupId"]
        print(f"created security group: {sg_id}")

        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[{
                "IpProtocol": "tcp",
                "FromPort": 6379,
                "ToPort": 6379,
                "IpRanges": [{"CidrIp": "172.31.0.0/16"}],
            }],
        )
        print("allowed inbound 6379 from VPC")
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
