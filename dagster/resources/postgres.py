"""PostgreSQL access for Dagster assets (asyncpg)."""

import os

import asyncpg
from dagster import ConfigurableResource

from common.postgres import get_all_tickers


class PostgresResource(ConfigurableResource):
    """Application Postgres (tickers, positions), not Dagster metadata DB."""

    database_url: str = ""

    def _url(self) -> str:
        u = self.database_url or os.environ.get("DATABASE_URL", "")
        if not u:
            raise ValueError("PostgresResource.database_url or DATABASE_URL must be set")
        return u

    async def fetch_all_tickers(self) -> list[str]:
        conn = await asyncpg.connect(self._url())
        try:
            return await get_all_tickers(conn)
        finally:
            await conn.close()
