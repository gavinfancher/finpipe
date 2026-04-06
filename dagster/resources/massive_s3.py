"""Massive S3 resource — provides an S3 client pointed at files.massive.com."""

import os

import boto3
from botocore.config import Config
from dagster import ConfigurableResource


class MassiveS3Resource(ConfigurableResource):
    """S3 client for the Massive flat file API (files.massive.com)."""

    access_key: str = ""
    secret_key: str = ""

    def get_client(self):
        session = boto3.Session(
            aws_access_key_id=self.access_key or os.environ.get("MASSIVE_ACCESS_KEY", ""),
            aws_secret_access_key=self.secret_key or os.environ.get("MASSIVE_SECRET_KEY", ""),
        )
        return session.client(
            "s3",
            endpoint_url="https://files.massive.com",
            config=Config(signature_version="s3v4"),
        )

    def list_keys(self, prefix: str) -> list[str]:
        """List all file keys under a prefix in the flatfiles bucket."""
        client = self.get_client()
        keys = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket="flatfiles", Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return sorted(keys)
