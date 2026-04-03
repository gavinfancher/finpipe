"""
Create IAM role, instance profile, and security group for the finpipe streaming EC2 instance.

Usage:
    uv run python deploy/ec2/setup_aws.py
"""

import json
import boto3

iam = boto3.client("iam")
ec2 = boto3.client("ec2", region_name="us-east-1")

ROLE_NAME = "finpipe-ec2-role"
PROFILE_NAME = "finpipe-ec2-profile"
SG_NAME = "finpipe-ec2-sg"
RDS_SG_ID = "sg-0b33b31da3faad9b5"  # finpipe-rds-sg
VPC_ID = "vpc-0d17c300bee12bf9f"
ACCOUNT_ID = "809000566572"


# ---------- IAM role + instance profile ----------

trust_policy = {
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "ec2.amazonaws.com"},
        "Action": "sts:AssumeRole",
    }],
}

try:
    iam.create_role(
        RoleName=ROLE_NAME,
        AssumeRolePolicyDocument=json.dumps(trust_policy),
    )
    print(f"created role: {ROLE_NAME}")
except iam.exceptions.EntityAlreadyExistsException:
    print(f"role already exists: {ROLE_NAME}")

# Secrets Manager access
iam.put_role_policy(
    RoleName=ROLE_NAME,
    PolicyName="secrets-access",
    PolicyDocument=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": "secretsmanager:GetSecretValue",
            "Resource": f"arn:aws:secretsmanager:us-east-1:{ACCOUNT_ID}:secret:finpipe/*",
        }],
    }),
)
print("attached secrets manager policy")

# RDS describe (for user-data to get endpoint)
iam.put_role_policy(
    RoleName=ROLE_NAME,
    PolicyName="rds-describe",
    PolicyDocument=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": "rds:DescribeDBInstances",
            "Resource": f"arn:aws:rds:us-east-1:{ACCOUNT_ID}:db:finpipe-db",
        }],
    }),
)
print("attached rds describe policy")

# SSM for remote access
iam.attach_role_policy(
    RoleName=ROLE_NAME,
    PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
)
print("attached ssm policy")

# Instance profile
try:
    iam.create_instance_profile(InstanceProfileName=PROFILE_NAME)
    iam.add_role_to_instance_profile(
        InstanceProfileName=PROFILE_NAME,
        RoleName=ROLE_NAME,
    )
    print(f"created instance profile: {PROFILE_NAME}")
except iam.exceptions.EntityAlreadyExistsException:
    print(f"instance profile already exists: {PROFILE_NAME}")


# ---------- Security group ----------

try:
    sg = ec2.create_security_group(
        GroupName=SG_NAME,
        Description="finpipe streaming EC2 — no inbound, HTTPS + RDS outbound",
        VpcId=VPC_ID,
    )
    sg_id = sg["GroupId"]
    print(f"created security group: {sg_id}")

    # Remove default allow-all outbound
    ec2.revoke_security_group_egress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "-1",
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        }],
    )

    # Outbound: HTTPS (cloudflared, docker pulls, etc.)
    ec2.authorize_security_group_egress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "tcp",
            "FromPort": 443,
            "ToPort": 443,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        }],
    )

    # Outbound: HTTP (package installs)
    ec2.authorize_security_group_egress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "tcp",
            "FromPort": 80,
            "ToPort": 80,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        }],
    )

    # Outbound: Postgres to RDS security group
    ec2.authorize_security_group_egress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "tcp",
            "FromPort": 5432,
            "ToPort": 5432,
            "UserIdGroupPairs": [{"GroupId": RDS_SG_ID}],
        }],
    )
    print("configured outbound rules (HTTPS + HTTP + RDS)")

    # Allow RDS SG to accept inbound from this EC2 SG
    ec2.authorize_security_group_ingress(
        GroupId=RDS_SG_ID,
        IpPermissions=[{
            "IpProtocol": "tcp",
            "FromPort": 5432,
            "ToPort": 5432,
            "UserIdGroupPairs": [{"GroupId": sg_id}],
        }],
    )
    print(f"allowed RDS inbound from {sg_id}")

except Exception as e:
    if "already exists" in str(e):
        print(f"security group already exists: {SG_NAME}")
        sgs = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": [SG_NAME]}])
        sg_id = sgs["SecurityGroups"][0]["GroupId"]
    else:
        raise


# ---------- done ----------

print()
print("=== ready ===")
print(f"instance profile: {PROFILE_NAME}")
print(f"security group:   {sg_id}")
print()
print("launch with:")
print(f'  aws ec2 run-instances \\')
print(f'    --image-id <ami-id> \\')
print(f'    --instance-type t3.medium \\')
print(f'    --iam-instance-profile Name={PROFILE_NAME} \\')
print(f'    --security-group-ids {sg_id} \\')
print(f'    --subnet-id subnet-074afec090850ea1a \\')
print(f'    --user-data file://deploy/ec2/user-data.sh')
