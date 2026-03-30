"""
Tick enrichment using Redis-cached performance data.
Historical closes and perf metrics are written to Redis by the close-of-day job.
"""

import logging

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_rdb: aioredis.Redis | None = None

# Redis key patterns
PREV_CLOSE_KEY = "ticker:prev_close:{}"
PERF_KEY = "ticker:perf:{}"
PRICE_KEY = "ticker:prices:{}"

_PERF_FIELDS = ("perf5d", "perf1m", "perf3m", "perf6m", "perf1y", "perfYtd", "perf3y")
_CLOSE_FIELDS = ("5d", "1m", "3m", "6m", "1y", "ytd", "3y")


async def init_redis(redis_url: str):
    global _rdb
    _rdb = aioredis.from_url(redis_url, decode_responses=True)
    logger.info("enrichment redis connected")


async def close_redis():
    if _rdb:
        await _rdb.close()


async def enrich_tick(tick: dict) -> dict:
    """Enrich a tick with change/perf data from Redis cache."""
    if not _rdb:
        return tick

    price = tick["price"]
    ticker = tick["ticker"]

    # Get previous close from Redis
    prev_str = await _rdb.get(PREV_CLOSE_KEY.format(ticker))
    if prev_str:
        prev = float(prev_str)
        change = price - prev
        tick["change"] = round(change, 4)
        tick["changePct"] = round(change / prev * 100, 4)
        tick["prevClose"] = prev

    # Get perf reference closes from Redis
    perf_data = await _rdb.hgetall(PERF_KEY.format(ticker))
    if perf_data:
        for perf_field, close_field in zip(_PERF_FIELDS, _CLOSE_FIELDS):
            ref_str = perf_data.get(close_field)
            if ref_str:
                ref = float(ref_str)
                if ref:
                    tick[perf_field] = round((price - ref) / ref * 100, 4)

    # Update latest price in Redis cache
    await _rdb.hset(PRICE_KEY.format(ticker), mapping={
        "price": str(price),
        "change": str(tick.get("change", 0)),
        "changePct": str(tick.get("changePct", 0)),
        "volume": str(tick.get("volume", 0)),
        "timestamp": str(tick.get("timestamp", 0)),
    })

    return tick


async def get_cached_tick(ticker: str) -> dict | None:
    """Get cached price data for a ticker (for off-hours additions)."""
    if not _rdb:
        return None
    data = await _rdb.hgetall(PRICE_KEY.format(ticker))
    if not data:
        return None
    return {
        "ticker": ticker,
        "price": float(data.get("price", 0)),
        "change": float(data.get("change", 0)),
        "changePct": float(data.get("changePct", 0)),
        "volume": int(float(data.get("volume", 0))),
        "timestamp": int(float(data.get("timestamp", 0))),
    }
