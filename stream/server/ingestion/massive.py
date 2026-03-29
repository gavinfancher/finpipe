"""
Ingestion node: connects to Massive and streams ticks to the relay.

The relay connects via WS /stream and can send subscription commands:
  {"action": "subscribe",   "ticker": "AAPL"}
  {"action": "unsubscribe", "ticker": "AAPL"}

Run: uv run uvicorn server.ingestion.massive:app --port 9000
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from massive import WebSocketClient
from massive.websocket.models import EquityAgg, Feed, Market

from server.config import MASSIVE_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = WebSocketClient(
    api_key=MASSIVE_API_KEY,
    feed=Feed.Delayed,
    market=Market.Stocks,
)

ticks: dict = {}
subscriptions: set[str] = set()
relays: set[WebSocket] = set()

DEFAULT_TICKERS = ["A.SPY"]


def normalize(ticker: str) -> str:
    ticker = ticker.upper().strip()
    if not ticker.startswith("A."):
        ticker = f"A.{ticker}"
    return ticker


async def broadcast(data: dict):
    dead = set()
    for ws in relays:
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    relays.difference_update(dead)


async def handle_msg(msgs):
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
        }
        ticks[display_ticker] = tick
        await broadcast({"type": "tick", "tick": tick})


async def run_massive():
    while True:
        try:
            logger.info("massive: connecting...")
            await client.connect(handle_msg)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("massive: disconnected (%s), retrying in 5s", e)
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    for t in DEFAULT_TICKERS:
        subscriptions.add(t)
        client.subscribe(t)
    task = asyncio.create_task(run_massive())
    yield
    await client.close()
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/stream")
async def stream_endpoint(ws: WebSocket):
    await ws.accept()
    relays.add(ws)
    logger.info("relay connected, pool=%d", len(relays))
    try:
        if ticks:
            await ws.send_json({"type": "snapshot", "ticks": ticks})
        display_subs = sorted(s.removeprefix("A.") for s in subscriptions)
        await ws.send_json({"type": "tickers", "tickers": display_subs})
        while True:
            data = await ws.receive_json()
            action = data.get("action")
            ticker = data.get("ticker", "")
            sub = normalize(ticker)
            if action == "subscribe" and sub not in subscriptions:
                subscriptions.add(sub)
                client.subscribe(sub)
                logger.info("subscribed: %s", sub)
                display_subs = sorted(s.removeprefix("A.") for s in subscriptions)
                await broadcast({"type": "tickers", "tickers": display_subs})
            elif action == "unsubscribe":
                subscriptions.discard(sub)
                ticks.pop(ticker.upper(), None)
                client.unsubscribe(sub)
                logger.info("unsubscribed: %s", sub)
                display_subs = sorted(s.removeprefix("A.") for s in subscriptions)
                await broadcast({"type": "tickers", "tickers": display_subs})
    except Exception:
        pass
    finally:
        relays.discard(ws)
        logger.info("relay disconnected, pool=%d", len(relays))


@app.get("/health")
def health():
    return {
        "status": "ok",
        "subscriptions": sorted(subscriptions),
        "tick_count": len(ticks),
        "relays": len(relays),
    }
