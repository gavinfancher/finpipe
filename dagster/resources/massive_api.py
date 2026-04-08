"""Massive REST API client as a Dagster resource."""

import os

from dagster import ConfigurableResource
from massive import RESTClient


class MassiveAPIResource(ConfigurableResource):
    """Massive market data REST API."""

    api_key: str = ""

    def get_client(self) -> RESTClient:
        key = self.api_key or os.environ.get("MASSIVE_API_KEY", "")
        if not key:
            raise ValueError("MassiveAPIResource.api_key or MASSIVE_API_KEY must be set")
        return RESTClient(api_key=key)
