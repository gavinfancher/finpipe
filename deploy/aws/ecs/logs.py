"""
Create the /ecs/finpipe-ingest CloudWatch log group.

Usage:
    uv run python deploy/aws/ecs/logs.py
"""

from deploy.aws.config import logs

LOG_GROUP = "/ecs/finpipe-ingest"


def create() -> str:
    """Create or find the CloudWatch log group. Returns the log group name."""
    try:
        logs.create_log_group(logGroupName=LOG_GROUP)
        logs.put_retention_policy(logGroupName=LOG_GROUP, retentionInDays=7)
        print(f"created log group: {LOG_GROUP}")
    except logs.exceptions.ResourceAlreadyExistsException:
        print(f"already exists: {LOG_GROUP}")

    return LOG_GROUP


if __name__ == "__main__":
    create()
