"""
Relay: connects to the ingestion node and broadcasts enriched ticks to UI WebSocket clients.
"""

import asyncio
import json
import logging

import websockets

from server.config import CONSUMER_URL
from server.pipeline import state
from server.pipeline.enrichment import enrich_tick

logger = logging.getLogger(__name__)


async def broadcast_ui(data: dict):
    dead = set()
    for ws in state.ui_clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    state.ui_clients.difference_update(dead)


async def send_to_consumer(data: dict):
    if state._consumer_ws is not None:
        try:
            await state._consumer_ws.send(json.dumps(data))
        except Exception as e:
            logger.error("send_to_consumer failed: %s", e)


async def run(startup_tickers: list[str]):
    while True:
        try:
            logger.info("relay: connecting to %s", CONSUMER_URL)
            async with websockets.connect(CONSUMER_URL) as ws:
                state._consumer_ws = ws
                logger.info("relay: connected")
                for ticker in startup_tickers:
                    await ws.send(json.dumps({"action": "subscribe", "ticker": ticker}))
                async for raw in ws:
                    msg = json.loads(raw)
                    msg_type = msg.get("type")
                    if msg_type == "snapshot":
                        enriched = {k: enrich_tick(v) for k, v in msg["ticks"].items()}
                        state.ticks = enriched
                        msg["ticks"] = enriched
                    elif msg_type == "tickers":
                        state.subscriptions = msg["tickers"]
                    elif msg_type == "tick":
                        tick = enrich_tick(msg["tick"])
                        state.ticks[tick["ticker"]] = tick
                        msg["tick"] = tick
                    await broadcast_ui(msg)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("relay: disconnected (%s), retrying in 3s", e)
            state._consumer_ws = None
        await asyncio.sleep(3)
