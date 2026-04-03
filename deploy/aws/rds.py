"""
Provision the finpipe RDS Postgres instance.

Creates:
  - Security group (finpipe-rds-sg) allowing 5432 from within VPC
  - DB subnet group (us-east-1a + us-east-1b)
  - RDS instance (db.t4g.micro, Postgres 17, gp3, private)

Usage:
    uv run python deploy/aws/rds.py

Requires FINPIPE_DB_PASSWORD env var for the master password.
"""

import json
import os
import sys

import boto3

ec2 = boto3.client("ec2", region_name="us-east-1")
rds = boto3.client("rds", region_name="us-east-1")

VPC_ID = "vpc-0d17c300bee12bf9f"
SUBNET_1A = "subnet-074afec090850ea1a"  # us-east-1a
SUBNET_1B = "subnet-097b8d2beacf96f1b"  # us-east-1b
AZ = "us-east-1a"

SG_NAME = "finpipe-rds-sg"
SUBNET_GROUP_NAME = "finpipe-rds-subnet"
DB_INSTANCE_ID = "finpipe-db"
DB_NAME = "finpipe"

DB_PASSWORD = os.environ.get("FINPIPE_DB_PASSWORD")
if not DB_PASSWORD:
    print("error: set FINPIPE_DB_PASSWORD env var")
    sys.exit(1)


# ---------- security group ----------

try:
    sg = ec2.create_security_group(
        GroupName=SG_NAME,
        Description="Postgres access from within VPC only",
        VpcId=VPC_ID,
    )
    sg_id = sg["GroupId"]
    print(f"created security group: {sg_id}")

    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "tcp",
            "FromPort": 5432,
            "ToPort": 5432,
            "IpRanges": [{"CidrIp": "172.31.0.0/16"}],
        }],
    )
    print("allowed inbound 5432 from VPC")

except Exception as e:
    if "already exists" in str(e):
        sgs = ec2.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [SG_NAME]}],
        )
        sg_id = sgs["SecurityGroups"][0]["GroupId"]
        print(f"security group already exists: {sg_id}")
    else:
        raise


# ---------- db subnet group ----------

try:
    rds.create_db_subnet_group(
        DBSubnetGroupName=SUBNET_GROUP_NAME,
        DBSubnetGroupDescription="finpipe RDS subnets",
        SubnetIds=[SUBNET_1A, SUBNET_1B],
    )
    print(f"created db subnet group: {SUBNET_GROUP_NAME}")
except rds.exceptions.DBSubnetGroupAlreadyExistsFault:
    print(f"db subnet group already exists: {SUBNET_GROUP_NAME}")


# ---------- rds instance ----------

try:
    rds.create_db_instance(
        DBInstanceIdentifier=DB_INSTANCE_ID,
        DBInstanceClass="db.t4g.micro",
        Engine="postgres",
        EngineVersion="17",
        MasterUsername="postgres",
        MasterUserPassword=DB_PASSWORD,
        AllocatedStorage=20,
        StorageType="gp3",
        DBName=DB_NAME,
        DBSubnetGroupName=SUBNET_GROUP_NAME,
        VpcSecurityGroupIds=[sg_id],
        AvailabilityZone=AZ,
        PubliclyAccessible=False,
        MultiAZ=False,
        BackupRetentionPeriod=1,
        AutoMinorVersionUpgrade=False,
        Tags=[{"Key": "project", "Value": "finpipe"}],
    )
    print(f"creating rds instance: {DB_INSTANCE_ID}")
    print("this will take ~5 minutes...")

except rds.exceptions.DBInstanceAlreadyExistsFault:
    print(f"rds instance already exists: {DB_INSTANCE_ID}")


# ---------- wait + print endpoint ----------

print()
print("checking endpoint...")
waiter = rds.get_waiter("db_instance_available")
try:
    waiter.wait(
        DBInstanceIdentifier=DB_INSTANCE_ID,
        WaiterConfig={"Delay": 15, "MaxAttempts": 40},
    )
except Exception:
    print("timed out waiting — check with: aws rds describe-db-instances --db-instance-identifier finpipe-db")
    sys.exit(0)

db = rds.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
endpoint = db["DBInstances"][0]["Endpoint"]["Address"]

print()
print("=== ready ===")
print(f"endpoint:       {endpoint}")
print(f"port:           5432")
print(f"database:       {DB_NAME}")
print(f"user:           postgres")
print(f"security group: {sg_id}")
print()
print("connection string:")
print(f"  postgresql://postgres:$FINPIPE_DB_PASSWORD@{endpoint}:5432/{DB_NAME}")
