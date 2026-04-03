"""
Control node: manages ticker assignments across ingestion nodes.

- Runs an internal HTTP API for ingest node registration (port 8081)
- Queries PostgreSQL for all unique tickers (watchlists + positions)
- Maintains ticker→node assignments in Redis
- Balances tickers across live ingest nodes (≤100 per node, min 3, always odd)
- Publishes assignment changes via Redis pub/sub
- Scales ECS Fargate ingest service based on ticker count
- Detects market hours and scales to 0 outside trading sessions

Run: uv run python -m streaming.control
"""

import asyncio
import json
import logging
import math
import os
import time
from datetime import date

import asyncpg
import pandas_market_calendars as mcal
import redis.asyncio as aioredis
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from common.postgres import get_all_tickers as _get_all_tickers
from common.redis_keys import ASSIGNMENTS_KEY, CHANNEL, NODE_COUNT_KEY

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger("control")

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
POLL_INTERVAL = int(os.environ.get("CONTROL_POLL_INTERVAL", "5"))
MAX_TICKERS_PER_NODE = 100
MIN_NODES = int(os.environ.get("MIN_NODES", "3"))
CONTROL_PORT = int(os.environ.get("CONTROL_PORT", "8081"))
HEARTBEAT_TTL = int(os.environ.get("HEARTBEAT_TTL", "30"))  # seconds before node is considered dead

# ECS scaling — disabled when ECS_CLUSTER is not set (local dev)
ECS_CLUSTER = os.environ.get("ECS_CLUSTER", "")
ECS_SERVICE = os.environ.get("ECS_SERVICE", "ingest")
ECS_REGION = os.environ.get("AWS_REGION", "us-east-1")

_ecs_client = None
_nyse = mcal.get_calendar("NYSE")


# ---------- node registry ----------

class NodeInfo(BaseModel):
    node_id: str
    tickers: list[str] = []


class _Registry:
    """Tracks live ingest nodes via heartbeats."""

    def __init__(self, ttl: int):
        self.ttl = ttl
        self._nodes: dict[str, float] = {}  # node_id → last_heartbeat timestamp

    def register(self, node_id: str):
        self._nodes[node_id] = time.time()

    def heartbeat(self, node_id: str):
        self._nodes[node_id] = time.time()

    def deregister(self, node_id: str):
        self._nodes.pop(node_id, None)

    def live_nodes(self) -> list[str]:
        now = time.time()
        alive = [nid for nid, ts in self._nodes.items() if now - ts < self.ttl]
        # Clean up dead nodes
        dead = [nid for nid, ts in self._nodes.items() if now - ts >= self.ttl]
        for nid in dead:
            logger.warning("node %s missed heartbeat, removing", nid)
            del self._nodes[nid]
        return sorted(alive)

    def status(self) -> dict:
        now = time.time()
        return {
            node_id: {
                "last_heartbeat": int(now - ts),
                "alive": now - ts < self.ttl,
            }
            for node_id, ts in self._nodes.items()
        }


registry = _Registry(ttl=HEARTBEAT_TTL)


# ---------- internal API ----------

api = FastAPI(title="finpipe-control", docs_url=None, redoc_url=None)


@api.post("/register")
async def register_node(body: NodeInfo):
    registry.register(body.node_id)
    logger.info("node registered: %s", body.node_id)
    return {"status": "registered", "node_id": body.node_id}


@api.post("/heartbeat")
async def heartbeat_node(body: NodeInfo):
    registry.heartbeat(body.node_id)
    return {"status": "ok", "node_id": body.node_id}


@api.post("/deregister")
async def deregister_node(body: NodeInfo):
    registry.deregister(body.node_id)
    logger.info("node deregistered: %s", body.node_id)
    return {"status": "deregistered", "node_id": body.node_id}


@api.get("/health")
async def health():
    live = registry.live_nodes()
    return {
        "status": "ok",
        "live_nodes": len(live),
        "nodes": registry.status(),
        "market_open": is_market_open(),
        "ecs_enabled": bool(ECS_CLUSTER),
    }


# ---------- helpers ----------

def _get_ecs_client():
    """Lazy-init boto3 ECS client (only when ECS scaling is enabled)."""
    global _ecs_client
    if _ecs_client is None:
        import boto3
        _ecs_client = boto3.client("ecs", region_name=ECS_REGION)
    return _ecs_client


def is_market_open() -> bool:
    """Check if today is a NYSE trading session."""
    today = date.today()
    schedule = _nyse.schedule(start_date=today, end_date=today)
    return len(schedule) > 0


def compute_node_count(ticker_count: int) -> int:
    """Compute number of ingest nodes needed. Min 3, always odd."""
    needed = max(MIN_NODES, math.ceil(ticker_count / MAX_TICKERS_PER_NODE))
    if needed % 2 == 0:
        needed += 1
    return needed


def assign_tickers(tickers: list[str], node_count: int, live_nodes: list[str]) -> dict[str, list[str]]:
    """Round-robin assign tickers to nodes. Returns {node_id: [tickers]}.

    Uses live_nodes if available, otherwise generates node IDs from count.
    """
    if live_nodes and len(live_nodes) >= node_count:
        node_ids = live_nodes[:node_count]
    else:
        node_ids = [f"ingest-{i}" for i in range(node_count)]

    assignments: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for i, ticker in enumerate(sorted(tickers)):
        node_id = node_ids[i % len(node_ids)]
        assignments[node_id].append(ticker)
    return assignments


async def get_all_tickers(pool: asyncpg.Pool) -> list[str]:
    """Get all unique tickers across all users."""
    async with pool.acquire() as conn:
        return await _get_all_tickers(conn)


# ---------- sync + scale ----------

async def sync_assignments(pool: asyncpg.Pool, rdb: aioredis.Redis):
    """Sync ticker assignments to Redis and notify ingest nodes."""
    tickers = await get_all_tickers(pool)
    node_count = compute_node_count(len(tickers))

    live = registry.live_nodes()

    # Get current assignments from Redis
    current_raw = await rdb.hgetall(ASSIGNMENTS_KEY)
    current = {k.decode(): v.decode() for k, v in current_raw.items()} if current_raw else {}

    # Compute new assignments
    new_assignments = assign_tickers(tickers, node_count, live)

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

    # Scale ECS service to match computed node count
    scale_ecs_service(node_count)

    logger.info(
        "assignments updated: %d tickers across %d nodes (%d live)",
        len(tickers), node_count, len(live),
    )
    for node_id, node_tickers in new_assignments.items():
        logger.info("  %s: %d tickers", node_id, len(node_tickers))


def scale_ecs_service(desired: int):
    """Update ECS ingest service desired count if it differs from current."""
    if not ECS_CLUSTER:
        return

    client = _get_ecs_client()
    resp = client.describe_services(
        cluster=ECS_CLUSTER,
        services=[ECS_SERVICE],
    )

    if not resp["services"]:
        logger.warning("ecs service %s not found in cluster %s", ECS_SERVICE, ECS_CLUSTER)
        return

    current = resp["services"][0]["desiredCount"]
    if current == desired:
        return

    client.update_service(
        cluster=ECS_CLUSTER,
        service=ECS_SERVICE,
        desiredCount=desired,
    )
    logger.info("ecs scaled: %d → %d tasks", current, desired)


# ---------- main ----------

async def control_loop(pool: asyncpg.Pool, rdb: aioredis.Redis):
    """Main polling loop — runs alongside the API server."""
    ecs_enabled = bool(ECS_CLUSTER)
    logger.info(
        "control loop started, polling every %ds, ecs scaling %s",
        POLL_INTERVAL,
        f"enabled (cluster={ECS_CLUSTER})" if ecs_enabled else "disabled",
    )

    while True:
        try:
            if not is_market_open():
                logger.info("market closed — scaling to 0")
                scale_ecs_service(0)
                await rdb.delete(ASSIGNMENTS_KEY)
                await rdb.set(NODE_COUNT_KEY, 0)
            else:
                await sync_assignments(pool, rdb)
        except Exception as e:
            logger.error("sync error: %s", e)
        await asyncio.sleep(POLL_INTERVAL)


async def run():
    pool = await asyncpg.create_pool(DATABASE_URL)
    rdb = aioredis.from_url(REDIS_URL, decode_responses=False)

    logger.info("control node starting on port %d", CONTROL_PORT)

    # Start the internal API server
    config = uvicorn.Config(
        api,
        host="0.0.0.0",
        port=CONTROL_PORT,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    # Run API server and control loop concurrently
    try:
        await asyncio.gather(
            server.serve(),
            control_loop(pool, rdb),
        )
    finally:
        await pool.close()
        await rdb.close()


if __name__ == "__main__":
    asyncio.run(run())
