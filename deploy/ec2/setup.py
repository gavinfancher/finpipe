"""
Pull secrets from AWS Secrets Manager and resolve service endpoints
to generate the .env file for docker-compose.

Run on the EC2 instance after cloning the repo:
    uv run python deploy/ec2/setup.py

Re-run anytime to refresh secrets or pick up endpoint changes.
"""

import os

import boto3

REGION = "us-east-1"
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def get_secret(name: str) -> str:
    client = boto3.client("secretsmanager", region_name=REGION)
    return client.get_secret_value(SecretId=name)["SecretString"]


def get_rds_endpoint() -> str:
    client = boto3.client("rds", region_name=REGION)
    resp = client.describe_db_instances(DBInstanceIdentifier="finpipe-db")
    return resp["DBInstances"][0]["Endpoint"]["Address"]


def get_valkey_endpoint() -> str:
    client = boto3.client("elasticache", region_name=REGION)
    resp = client.describe_replication_groups(ReplicationGroupId="finpipe-cache")
    return resp["ReplicationGroups"][0]["NodeGroups"][0]["PrimaryEndpoint"]["Address"]



def create():
    print("resolving endpoints...")
    db_password = get_secret("finpipe/db-password")
    rds_endpoint = get_rds_endpoint()
    valkey_endpoint = get_valkey_endpoint()

    print("pulling secrets...")
    env = {
        "DATABASE_URL": f"postgresql://postgres:{db_password}@{rds_endpoint}:5432/finpipe",
        "REDIS_URL": f"redis://{valkey_endpoint}:6379",
        "JWT_SECRET": get_secret("finpipe/jwt-secret"),
        "BETA_KEY": get_secret("finpipe/beta-key"),
        "MASSIVE_API_KEY": get_secret("finpipe/massive"),
        "ADMIN_USER": "admin",
        "ADMIN_PASSWORD": get_secret("finpipe/admin-password"),
    }

    with open(ENV_PATH, "w") as f:
        for key, value in env.items():
            f.write(f"{key}={value}\n")

    os.chmod(ENV_PATH, 0o600)
    print(f"wrote {ENV_PATH} ({len(env)} vars)")

    # cloudflared tunnel credentials
    creds_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloudflared-credentials.json")
    creds = get_secret("finpipe/cloudflared-credentials")
    with open(creds_path, "w") as f:
        f.write(creds)
    os.chmod(creds_path, 0o600)
    print(f"wrote {creds_path}")


if __name__ == "__main__":
    create()
