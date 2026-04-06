"""
Create the finpipe-lakehouse S3 bucket.

Layout:
  s3://finpipe-lakehouse/bronze/staged/{ticker}/{date}.parquet  — raw from Massive
  s3://finpipe-lakehouse/iceberg/                               — Iceberg tables
  s3://finpipe-lakehouse/athena-results/                        — Athena query output

Usage:
    uv run python infra/s3/bucket.py
"""

from infra.config import s3, REGION, ACCOUNT_ID

BUCKET = "finpipe-lakehouse"


def create() -> str:
    """Create the lakehouse S3 bucket. Returns the bucket name."""
    try:
        if REGION == "us-east-1":
            s3.create_bucket(Bucket=BUCKET)
        else:
            s3.create_bucket(
                Bucket=BUCKET,
                CreateBucketConfiguration={"LocationConstraint": REGION},
            )
        print(f"created bucket: {BUCKET}")
    except s3.exceptions.BucketAlreadyOwnedByYou:
        print(f"already exists: {BUCKET}")

    # block public access
    s3.put_public_access_block(
        Bucket=BUCKET,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    print("  public access: blocked")

    # lifecycle: clean up staged files after 7 days
    s3.put_bucket_lifecycle_configuration(
        Bucket=BUCKET,
        LifecycleConfiguration={
            "Rules": [{
                "ID": "expire-staged",
                "Status": "Enabled",
                "Filter": {"Prefix": "bronze/staged/"},
                "Expiration": {"Days": 7},
            }],
        },
    )
    print("  lifecycle: bronze/staged/ expires after 7 days")

    return BUCKET


if __name__ == "__main__":
    create()
