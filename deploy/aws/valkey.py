"""
Provision the finpipe ElastiCache Valkey instance.

Creates:
  - Security group (finpipe-valkey-sg) allowing 6379 from within VPC
  - Subnet group (us-east-1a + us-east-1b)
  - ElastiCache node (cache.t4g.micro, Valkey 8, us-east-1a)

Usage:
    uv run python deploy/aws/valkey.py
"""

import sys
import time

import boto3

ec2 = boto3.client("ec2", region_name="us-east-1")
elasticache = boto3.client("elasticache", region_name="us-east-1")

VPC_ID = "vpc-0d17c300bee12bf9f"
SUBNET_1A = "subnet-074afec090850ea1a"  # us-east-1a
SUBNET_1B = "subnet-097b8d2beacf96f1b"  # us-east-1b
AZ = "us-east-1a"

SG_NAME = "finpipe-valkey-sg"
SUBNET_GROUP_NAME = "finpipe-valkey-subnet"
CLUSTER_ID = "finpipe-cache"


# ---------- security group ----------

try:
    sg = ec2.create_security_group(
        GroupName=SG_NAME,
        Description="Valkey access from within VPC only",
        VpcId=VPC_ID,
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

except Exception as e:
    if "already exists" in str(e):
        sgs = ec2.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [SG_NAME]}],
        )
        sg_id = sgs["SecurityGroups"][0]["GroupId"]
        print(f"security group already exists: {sg_id}")
    else:
        raise


# ---------- subnet group ----------

try:
    elasticache.create_cache_subnet_group(
        CacheSubnetGroupName=SUBNET_GROUP_NAME,
        CacheSubnetGroupDescription="finpipe Valkey subnets",
        SubnetIds=[SUBNET_1A, SUBNET_1B],
    )
    print(f"created subnet group: {SUBNET_GROUP_NAME}")
except elasticache.exceptions.CacheSubnetGroupAlreadyExistsFault:
    print(f"subnet group already exists: {SUBNET_GROUP_NAME}")


# ---------- cache cluster ----------

try:
    elasticache.create_cache_cluster(
        CacheClusterId=CLUSTER_ID,
        Engine="valkey",
        EngineVersion="8.0",
        CacheNodeType="cache.t4g.micro",
        NumCacheNodes=1,
        CacheSubnetGroupName=SUBNET_GROUP_NAME,
        SecurityGroupIds=[sg_id],
        PreferredAvailabilityZone=AZ,
        Tags=[{"Key": "project", "Value": "finpipe"}],
    )
    print(f"creating cache cluster: {CLUSTER_ID}")
    print("this will take ~5 minutes...")

except elasticache.exceptions.CacheClusterAlreadyExistsFault:
    print(f"cache cluster already exists: {CLUSTER_ID}")


# ---------- wait + print endpoint ----------

print()
print("checking endpoint...")

for _ in range(40):
    resp = elasticache.describe_cache_clusters(
        CacheClusterId=CLUSTER_ID,
        ShowCacheNodeInfo=True,
    )
    cluster = resp["CacheClusters"][0]
    status = cluster["CacheClusterStatus"]
    if status == "available":
        break
    print(f"  status: {status}")
    time.sleep(15)
else:
    print("timed out — check with: aws elasticache describe-cache-clusters --cache-cluster-id finpipe-cache")
    sys.exit(0)

node = cluster["CacheNodes"][0]
endpoint = node["Endpoint"]["Address"]
port = node["Endpoint"]["Port"]

print()
print("=== ready ===")
print(f"endpoint:       {endpoint}")
print(f"port:           {port}")
print(f"security group: {sg_id}")
print()
print("connection string:")
print(f"  redis://{endpoint}:{port}")
