"""Dagster resources for finpipe-dagster."""

import os

import boto3
from dagster import get_dagster_logger

from .emr import EMRServerlessResource
from .massive_s3 import MassiveS3Resource


def _get_secret(name: str, env_fallback: str = "") -> str:
    """Fetch a secret from AWS Secrets Manager, falling back to env/default for local dev."""
    env_val = os.environ.get(env_fallback)
    if env_val:
        return env_val
    try:
        client = boto3.client("secretsmanager", region_name="us-east-1")
        return client.get_secret_value(SecretId=name)["SecretString"]
    except Exception:
        return ""


def get_configured_resources() -> dict:
    """Return a dict of resource_key -> resource for Definitions()."""
    massive_key = _get_secret("finpipe/massive", "MASSIVE_API_KEY")

    return {
        "massive_s3": MassiveS3Resource(
            access_key=_get_secret("finpipe/massive-access-key", "MASSIVE_ACCESS_KEY"),
            secret_key=massive_key,
        ),
        "emr": EMRServerlessResource(
            execution_role_arn=_get_secret("finpipe/emr-role-arn", "EMR_ROLE_ARN"),
        ),
    }
