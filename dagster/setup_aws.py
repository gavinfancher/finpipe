"""
Create the IAM role, instance profile, and security group for the backfill EC2 instance.

Usage:
    uv run python setup_aws.py
"""

import json
import os
import boto3

iam = boto3.client("iam")
ec2 = boto3.client("ec2", region_name="us-east-1")
sm = boto3.client("secretsmanager", region_name="us-east-1")

ROLE_NAME = "backfill-ec2-role"
PROFILE_NAME = "backfill-ec2-profile"
SG_NAME = "backfill-sg"
BUCKET = "finpipe-root"
SECRET_NAME = "finpipe/massive"


# ---------- IAM role + instance profile ----------

trust_policy = {
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "ec2.amazonaws.com"},
        "Action": "sts:AssumeRole",
    }],
}

iam.create_role(
    RoleName=ROLE_NAME,
    AssumeRolePolicyDocument=json.dumps(trust_policy),
)
print(f"created role: {ROLE_NAME}")

iam.put_role_policy(
    RoleName=ROLE_NAME,
    PolicyName="s3-access",
    PolicyDocument=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
            "Resource": [
                f"arn:aws:s3:::{BUCKET}",
                f"arn:aws:s3:::{BUCKET}/*",
            ],
        }],
    }),
)
print("attached s3 policy")

iam.put_role_policy(
    RoleName=ROLE_NAME,
    PolicyName="secrets-access",
    PolicyDocument=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": "secretsmanager:GetSecretValue",
            "Resource": f"arn:aws:secretsmanager:us-east-1:*:secret:{SECRET_NAME}-*",
        }],
    }),
)
print("attached secrets manager policy")

iam.attach_role_policy(
    RoleName=ROLE_NAME,
    PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
)
print("attached ssm policy")

iam.create_instance_profile(InstanceProfileName=PROFILE_NAME)
iam.add_role_to_instance_profile(
    InstanceProfileName=PROFILE_NAME,
    RoleName=ROLE_NAME,
)
print(f"created instance profile: {PROFILE_NAME}")


# ---------- Security group ----------

sg = ec2.create_security_group(
    GroupName=SG_NAME,
    Description="SSH in, HTTPS out",
)
sg_id = sg["GroupId"]
print(f"created security group: {sg_id}")

# inbound: SSH
ec2.authorize_security_group_ingress(
    GroupId=sg_id,
    IpPermissions=[{
        "IpProtocol": "tcp",
        "FromPort": 22,
        "ToPort": 22,
        "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
    }],
)
print("allowed inbound SSH")

# outbound: replace default allow-all with HTTP + HTTPS only
ec2.revoke_security_group_egress(
    GroupId=sg_id,
    IpPermissions=[{
        "IpProtocol": "-1",
        "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
    }],
)
ec2.authorize_security_group_egress(
    GroupId=sg_id,
    IpPermissions=[
        {
            "IpProtocol": "tcp",
            "FromPort": 443,
            "ToPort": 443,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        },
        {
            "IpProtocol": "tcp",
            "FromPort": 80,
            "ToPort": 80,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        },
    ],
)
print("restricted outbound to HTTP + HTTPS only")


# ---------- Secrets Manager ----------

sm.create_secret(
    Name=SECRET_NAME,
    SecretString=json.dumps({
        "access_key": os.environ["MASSIVE_ACCESS_KEY"],
        "secret_key": os.environ["MASSIVE_SECRET_KEY"],
    }),
)
print(f"created secret: {SECRET_NAME}")


# ---------- done ----------

print()
print("=== ready ===")
print(f"instance profile: {PROFILE_NAME}")
print(f"security group:   {sg_id}")
print()
print("use these when launching an EC2 instance:")
print(f'  IamInstanceProfile={{"Name": "{PROFILE_NAME}"}}')
print(f'  SecurityGroupIds=["{sg_id}"]')
