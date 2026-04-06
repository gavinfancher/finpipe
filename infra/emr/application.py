"""
Create the finpipe EMR Serverless application.

Spark 3.5, auto-scales from 0, shuts down after 15 min idle.

Usage:
    uv run python infra/emr/application.py
"""

import boto3

from infra.config import REGION

emr = boto3.client("emr-serverless", region_name=REGION)

APP_NAME = "finpipe-spark"


def create() -> str:
    """Create or find the EMR Serverless application. Returns the application ID."""

    # check for existing
    resp = emr.list_applications()
    for app in resp.get("applications", []):
        if app["name"] == APP_NAME and app["state"] in ("CREATED", "STARTED", "STOPPED"):
            app_id = app["id"]
            print(f"already exists: {app_id} ({app['state']})")
            return app_id

    resp = emr.create_application(
        name=APP_NAME,
        releaseLabel="emr-7.1.0",
        type="SPARK",
        autoStartConfiguration={"enabled": True},
        autoStopConfiguration={"enabled": True, "idleTimeoutMinutes": 15},
        maximumCapacity={
            "cpu": "8 vCPU",
            "memory": "32 GB",
        },
        tags={"project": "finpipe"},
    )
    app_id = resp["applicationId"]
    print(f"created application: {app_id}")
    print(f"  release: emr-7.1.0 (Spark 3.5)")
    print(f"  auto-stop: 15 min idle")
    print(f"  max capacity: 8 vCPU, 32 GB")
    return app_id


if __name__ == "__main__":
    create()
