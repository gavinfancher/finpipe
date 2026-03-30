"""
Ingestion node: connects to Massive WS and produces ticks to Redpanda.

Each node subscribes to its assigned tickers (from Redis, set by control node).
Ticks are produced to the 'market-ticks' Redpanda/Kafka topic.

Run: NODE_ID=ingest-0 uv run python -m server.ingestion.massive
"""

import asyncio
import json
import logging
import os

import redis.asyncio as aioredis
from aiokafka import AIOKafkaProducer
from massive import WebSocketClient
from massive.websocket.models import EquityAgg, Feed, Market

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger("ingestion")

MASSIVE_API_KEY = os.environ.get("MASSIVE_API_KEY", "")
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
NODE_ID = os.environ.get("NODE_ID", "ingest-0")
TOPIC = "market-ticks"
CHANNEL = "control:assignments"
ASSIGNMENTS_KEY = "ticker:assignments"

client = WebSocketClient(
    api_key=MASSIVE_API_KEY,
    feed=Feed.Delayed,
    market=Market.Stocks,
)

producer: AIOKafkaProducer | None = None
current_tickers: set[str] = set()


def normalize(ticker: str) -> str:
    """Ensure ticker has A. prefix for Massive API."""
    ticker = ticker.upper().strip()
    if not ticker.startswith("A."):
        ticker = f"A.{ticker}"
    return ticker


async def handle_msg(msgs):
    """Handle messages from Massive WebSocket — produce to Kafka."""
    for m in msgs:
        if not isinstance(m, EquityAgg):
            continue
        if m.symbol is None or m.close is None:
            continue
        display_ticker = m.symbol.removeprefix("A.")
        open_price = m.official_open_price or m.open or m.close
        change = m.close - open_price
        change_pct = (change / open_price * 100) if open_price else 0.0
        tick = {
            "ticker": display_ticker,
            "price": m.close,
            "open": open_price,
            "change": change,
            "changePct": change_pct,
            "timestamp": m.end_timestamp or 0,
            "volume": m.accumulated_volume or 0,
            "node": NODE_ID,
        }
        if producer:
            await producer.send(
                TOPIC,
                key=display_ticker.encode(),
                value=json.dumps(tick).encode(),
            )


async def apply_assignments(tickers: list[str]):
    """Update Massive subscriptions to match assigned tickers."""
    global current_tickers
    new_set = set(tickers)
    to_add = new_set - current_tickers
    to_remove = current_tickers - new_set

    for ticker in to_remove:
        raw = normalize(ticker)
        client.unsubscribe(raw)
        logger.info("unsubscribed: %s", raw)

    for ticker in to_add:
        raw = normalize(ticker)
        client.subscribe(raw)
        logger.info("subscribed: %s", raw)

    current_tickers = new_set
    logger.info("active tickers: %d", len(current_tickers))


async def listen_for_assignments(rdb: aioredis.Redis):
    """Listen for assignment changes from control node via Redis pub/sub."""
    pubsub = rdb.pubsub()
    await pubsub.subscribe(CHANNEL)

    # Load initial assignments from Redis
    all_assignments = await rdb.hgetall(ASSIGNMENTS_KEY)
    my_tickers = [
        k.decode() for k, v in all_assignments.items()
        if v.decode() == NODE_ID
    ]
    if my_tickers:
        await apply_assignments(my_tickers)

    # Listen for updates
    async for msg in pubsub.listen():
        if msg["type"] != "message":
            continue
        try:
            data = json.loads(msg["data"])
            if data.get("node_id") == NODE_ID:
                await apply_assignments(data["tickers"])
        except Exception as e:
            logger.error("assignment parse error: %s", e)


async def run_massive():
    """Connect to Massive WebSocket with reconnection."""
    while True:
        try:
            logger.info("massive: connecting...")
            await client.connect(handle_msg)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("massive: disconnected (%s), retrying in 5s", e)
        await asyncio.sleep(5)


async def run():
    global producer

    rdb = aioredis.from_url(REDIS_URL, decode_responses=False)

    # Start Kafka producer
    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP)
    await producer.start()
    logger.info("kafka producer connected to %s", KAFKA_BOOTSTRAP)

    # Run Massive connection and assignment listener concurrently
    massive_task = asyncio.create_task(run_massive())
    assignment_task = asyncio.create_task(listen_for_assignments(rdb))

    try:
        await asyncio.gather(massive_task, assignment_task)
    except asyncio.CancelledError:
        pass
    finally:
        massive_task.cancel()
        assignment_task.cancel()
        await producer.stop()
        await rdb.close()
        await client.close()


if __name__ == "__main__":
    logger.info("starting %s", NODE_ID)
    asyncio.run(run())
