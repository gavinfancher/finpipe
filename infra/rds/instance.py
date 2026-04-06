"""
Provision the finpipe-db RDS Postgres instance.

Requires:
  - finpipe-rds-sg security group (infra/rds/sg.py)
  - finpipe-rds-subnet DB subnet group (infra/rds/subnet.py)
  - finpipe/db-password secret in Secrets Manager

Usage:
    uv run python infra/rds/instance.py
"""

import sys

import boto3

from infra.config import rds, REGION, AZ, find_sg

DB_INSTANCE_ID = "finpipe-db"
DB_NAME = "finpipe"
SG_NAME = "finpipe-rds-sg"
SUBNET_GROUP_NAME = "finpipe-rds-subnet"

sm = boto3.client("secretsmanager", region_name=REGION)


def create() -> str:
    """Create or find the RDS instance. Returns the endpoint address."""
    try:
        db_password = sm.get_secret_value(SecretId="finpipe/db-password")["SecretString"]
    except sm.exceptions.ResourceNotFoundException:
        print("error: secret finpipe/db-password not found in Secrets Manager")
        print("create it with:")
        print(f"  aws secretsmanager create-secret --name finpipe/db-password --secret-string '<password>' --region {REGION}")
        sys.exit(1)

    sg_id = find_sg(SG_NAME)
    if not sg_id:
        print(f"error: security group {SG_NAME} not found — run rds/sg.py first")
        sys.exit(1)

    try:
        rds.create_db_instance(
            DBInstanceIdentifier=DB_INSTANCE_ID,
            DBInstanceClass="db.t4g.micro",
            Engine="postgres",
            EngineVersion="17",
            MasterUsername="postgres",
            MasterUserPassword=db_password,
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
        print(f"already exists: {DB_INSTANCE_ID}")

    # wait for endpoint
    print("waiting for endpoint...")
    waiter = rds.get_waiter("db_instance_available")
    try:
        waiter.wait(
            DBInstanceIdentifier=DB_INSTANCE_ID,
            WaiterConfig={"Delay": 15, "MaxAttempts": 40},
        )
    except Exception:
        print("timed out — check: aws rds describe-db-instances --db-instance-identifier finpipe-db")
        sys.exit(0)

    db = rds.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
    endpoint = db["DBInstances"][0]["Endpoint"]["Address"]

    print()
    print(f"endpoint: {endpoint}")
    print(f"port:     5432")
    print(f"database: {DB_NAME}")
    print(f"user:     postgres")
    print(f"sg:       {sg_id}")
    return endpoint


if __name__ == "__main__":
    create()
