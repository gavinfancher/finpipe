"""
Relay: consumes ticks from Redpanda, enriches via Redis, broadcasts to UI WebSocket clients.
"""

import asyncio
import json
import logging
import os

from aiokafka import AIOKafkaConsumer

from pipeline import state
from pipeline.enrichment import enrich_tick

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC = "market-ticks"


async def broadcast_ui(data: dict):
    """Send data to all connected UI WebSocket clients."""
    dead = set()
    for ws in state.ui_clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    state.ui_clients.difference_update(dead)


async def run():
    """Consume from Redpanda and broadcast enriched ticks to UI."""
    consumer = AIOKafkaConsumer(
        TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id="ws-relay",
        value_deserializer=lambda v: json.loads(v),
        auto_offset_reset="latest",
    )

    while True:
        try:
            await consumer.start()
            logger.info("relay: consuming from %s topic=%s", KAFKA_BOOTSTRAP, TOPIC)

            async for msg in consumer:
                tick = msg.value
                enriched = await enrich_tick(tick)
                state.ticks[enriched["ticker"]] = enriched
                await broadcast_ui({"type": "tick", "tick": enriched})

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("relay: error (%s), retrying in 3s", e)
        finally:
            try:
                await consumer.stop()
            except Exception:
                pass
        await asyncio.sleep(3)
