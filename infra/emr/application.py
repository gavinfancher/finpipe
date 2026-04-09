"""
Create the finpipe EMR Serverless application.

Spark 3.5.x, auto-scales from 0, shuts down after 15 min idle.

Amazon EMR 7.1.x reaches end of standard support on 2026-08-01; this repo pins a
current 7.x line. See: https://docs.aws.amazon.com/emr/latest/EMR-Serverless-UserGuide/release-versions.html

Usage:
    uv run python infra/emr/application.py              # create or print existing id
    uv run python infra/emr/application.py update-capacity
    uv run python infra/emr/application.py update-release   # app must be STOPPED or CREATED
"""

import uuid

import boto3

from infra.config import REGION

emr = boto3.client("emr-serverless", region_name=REGION)

APP_NAME = "finpipe-spark"
# Latest EMR Serverless 7.x as of AWS docs (Spark 3.5.6); avoid 7.1.x (EoS 2026-08-01).
RELEASE_LABEL = "emr-7.12.0"


def create() -> str:
    """Create or find the EMR Serverless application. Returns the application ID."""

    # check for existing
    resp = emr.list_applications()
    for app in resp.get("applications", []):
        if app["name"] == APP_NAME and app["state"] in ("CREATED", "STARTED", "STOPPED"):
            app_id = app["id"]
            current = app.get("releaseLabel", "?")
            print(f"already exists: {app_id} ({app['state']}) release={current}")
            if current != RELEASE_LABEL:
                print(
                    f"  note: pinned release is {RELEASE_LABEL}; "
                    f"run: uv run python infra/emr/application.py update-release"
                )
            return app_id

    resp = emr.create_application(
        name=APP_NAME,
        releaseLabel=RELEASE_LABEL,
        type="SPARK",
        autoStartConfiguration={"enabled": True},
        autoStopConfiguration={"enabled": True, "idleTimeoutMinutes": 15},
        maximumCapacity={
            "cpu": "16 vCPU",
            "memory": "64 GB",
        },
        tags={"project": "finpipe"},
    )
    app_id = resp["applicationId"]
    print(f"created application: {app_id}")
    print(f"  release: {RELEASE_LABEL} (see AWS docs for Spark patch level)")
    print(f"  auto-stop: 15 min idle")
    print(f"  max capacity: 16 vCPU, 64 GB")
    return app_id


def update_max_capacity(cpu: str = "16 vCPU", memory: str = "64 GB") -> None:
    """Raise caps on an existing application (needed if created with older defaults)."""
    resp = emr.list_applications()
    app_id = None
    for app in resp.get("applications", []):
        if app["name"] == APP_NAME and app["state"] in ("CREATED", "STARTED", "STOPPED"):
            app_id = app["id"]
            break
    if not app_id:
        raise SystemExit(f"no application named {APP_NAME!r}")
    emr.update_application(
        applicationId=app_id,
        maximumCapacity={"cpu": cpu, "memory": memory},
    )
    print(f"updated {app_id}: maximumCapacity cpu={cpu} memory={memory}")


def update_release(release_label: str | None = None) -> None:
    """Switch an existing application to a newer EMR release (in-place).

    Application state must be **STOPPED** or **CREATED** (not STARTED / terminating).
    """
    label = release_label or RELEASE_LABEL
    resp = emr.list_applications()
    app_id = None
    state = None
    for app in resp.get("applications", []):
        if app["name"] == APP_NAME and app["state"] in ("CREATED", "STARTED", "STOPPED"):
            app_id = app["id"]
            state = app["state"]
            break
    if not app_id:
        raise SystemExit(f"no application named {APP_NAME!r}")
    if state not in ("STOPPED", "CREATED"):
        raise SystemExit(
            f"application {app_id} is {state!r}; wait until STOPPED (or stop jobs) then retry"
        )
    emr.update_application(
        applicationId=app_id,
        releaseLabel=label,
        clientToken=str(uuid.uuid4()),
    )
    print(f"updated {app_id}: releaseLabel={label}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "update-capacity":
        update_max_capacity()
    elif len(sys.argv) > 1 and sys.argv[1] == "update-release":
        update_release()
    else:
        create()
