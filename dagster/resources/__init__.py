"""Dagster resources for finpipe-dagster."""

import os

from .emr import EMRServerlessResource
from .massive_s3 import MassiveS3Resource


def get_configured_resources() -> dict:
    """Return a dict of resource_key -> resource for Definitions()."""
    return {
        "massive_s3": MassiveS3Resource(
            access_key=os.environ.get("MASSIVE_ACCESS_KEY", ""),
            secret_key=os.environ.get("MASSIVE_SECRET_KEY", ""),
        ),
        "emr": EMRServerlessResource(
            application_id=os.environ.get("EMR_APP_ID", ""),
            execution_role_arn=os.environ.get("EMR_ROLE_ARN", ""),
        ),
    }
