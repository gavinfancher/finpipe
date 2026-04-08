"""Redis connection as a Dagster resource."""

import os

import redis
from dagster import ConfigurableResource


class RedisResource(ConfigurableResource):
    """Valkey/Redis for ticker cache and control-plane keys."""

    url: str = ""

    def get_client(self) -> redis.Redis:
        u = self.url or os.environ.get("REDIS_URL", "redis://localhost:6379")
        return redis.from_url(u, decode_responses=True)
