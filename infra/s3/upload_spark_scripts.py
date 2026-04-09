"""
Upload PySpark driver scripts to the lakehouse bucket for EMR Serverless.

EMR expects:
  s3://finpipe-lakehouse/scripts/staged_to_bronze.py
  s3://finpipe-lakehouse/scripts/bronze_to_silver.py

Usage (from repo root, with AWS credentials):
    uv run python infra/s3/upload_spark_scripts.py
"""

from pathlib import Path

from infra.config import s3

BUCKET = "finpipe-lakehouse"
PREFIX = "scripts"

REPO_ROOT = Path(__file__).resolve().parents[2]
FILES = [
    REPO_ROOT / "dagster/spark/staged_to_bronze.py",
    REPO_ROOT / "dagster/spark/bronze_to_silver.py",
]


def main() -> None:
    for path in FILES:
        if not path.is_file():
            raise FileNotFoundError(path)
        key = f"{PREFIX}/{path.name}"
        print(f"upload {path.name} -> s3://{BUCKET}/{key}")
        s3.upload_file(str(path), BUCKET, key)
    print("done")


if __name__ == "__main__":
    main()
