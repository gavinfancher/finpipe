"""
Control node: manages ticker assignments across ingestion nodes.

- Queries PostgreSQL for all unique tickers (watchlists + positions)
- Maintains ticker→node assignments in Redis
- Balances tickers across ingest nodes (≤100 per node, min 3, always odd)
- Deduplicates subscriptions
- Publishes assignment changes via Redis pub/sub

Run: uv run python -m server.control.main
"""

import asyncio
import json
import logging
import math
import os

import asyncpg
import redis.asyncio as aioredis

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger("control")

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
POLL_INTERVAL = int(os.environ.get("CONTROL_POLL_INTERVAL", "5"))
MAX_TICKERS_PER_NODE = 100
MIN_NODES = 3

# Redis keys
ASSIGNMENTS_KEY = "ticker:assignments"        # hash: ticker → node_id
NODE_COUNT_KEY = "control:node_count"          # int: how many ingest nodes
CHANNEL = "control:assignments"               # pub/sub channel


def compute_node_count(ticker_count: int) -> int:
    """Compute number of ingest nodes needed. Min 3, always odd."""
    needed = max(MIN_NODES, math.ceil(ticker_count / MAX_TICKERS_PER_NODE))
    if needed % 2 == 0:
        needed += 1
    return needed


def assign_tickers(tickers: list[str], node_count: int) -> dict[str, list[str]]:
    """Round-robin assign tickers to nodes. Returns {node_id: [tickers]}."""
    assignments: dict[str, list[str]] = {f"ingest-{i}": [] for i in range(node_count)}
    node_ids = list(assignments.keys())
    for i, ticker in enumerate(sorted(tickers)):
        node_id = node_ids[i % node_count]
        assignments[node_id].append(ticker)
    return assignments


async def get_all_tickers(pool: asyncpg.Pool) -> list[str]:
    """Get all unique tickers across all users."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            select distinct ticker from user_tickers
            union
            select distinct ticker from positions
            order by ticker
        """)
    return [r["ticker"] for r in rows]


async def sync_assignments(pool: asyncpg.Pool, rdb: aioredis.Redis):
    """Sync ticker assignments to Redis and notify ingest nodes."""
    tickers = await get_all_tickers(pool)
    node_count = compute_node_count(len(tickers))

    # Get current assignments from Redis
    current_raw = await rdb.hgetall(ASSIGNMENTS_KEY)
    current = {k.decode(): v.decode() for k, v in current_raw.items()} if current_raw else {}

    # Compute new assignments
    new_assignments = assign_tickers(tickers, node_count)

    # Build new ticker→node map
    new_map: dict[str, str] = {}
    for node_id, node_tickers in new_assignments.items():
        for ticker in node_tickers:
            new_map[ticker] = node_id

    # Check if anything changed
    if new_map == current:
        return

    # Update Redis atomically
    pipe = rdb.pipeline()
    pipe.delete(ASSIGNMENTS_KEY)
    if new_map:
        pipe.hset(ASSIGNMENTS_KEY, mapping=new_map)
    pipe.set(NODE_COUNT_KEY, node_count)
    await pipe.execute()

    # Publish per-node assignment lists so each node knows its tickers
    for node_id, node_tickers in new_assignments.items():
        await rdb.publish(CHANNEL, json.dumps({
            "node_id": node_id,
            "tickers": node_tickers,
            "node_count": node_count,
        }))

    logger.info(
        "assignments updated: %d tickers across %d nodes",
        len(tickers), node_count,
    )
    for node_id, node_tickers in new_assignments.items():
        logger.info("  %s: %d tickers", node_id, len(node_tickers))


async def run():
    pool = await asyncpg.create_pool(DATABASE_URL)
    rdb = aioredis.from_url(REDIS_URL, decode_responses=False)

    logger.info("control node started, polling every %ds", POLL_INTERVAL)

    try:
        while True:
            try:
                await sync_assignments(pool, rdb)
            except Exception as e:
                logger.error("sync error: %s", e)
            await asyncio.sleep(POLL_INTERVAL)
    finally:
        await pool.close()
        await rdb.close()


if __name__ == "__main__":
    asyncio.run(run())
