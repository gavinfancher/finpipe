"""
Tick enrichment using Redis-cached performance data.
Historical closes and perf metrics are written to Redis by the close-of-day job.
"""

import asyncio
import logging
import os
from datetime import date, timedelta

import redis.asyncio as aioredis
from common.market import PERF_PERIODS, trading_dates
from common.redis_keys import (
    CLOSE_FIELDS,
    PERF_FIELDS,
    PERF_KEY,
    PREV_CLOSE_KEY,
    PRICE_KEY,
)

logger = logging.getLogger(__name__)

_rdb: aioredis.Redis | None = None


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
        for perf_field, close_field in zip(PERF_FIELDS, CLOSE_FIELDS):
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


async def add_perf_fields(tick: dict) -> dict:
    """Add perf percentage fields to a tick without touching change/changePct.

    Unlike enrich_tick, this does NOT re-derive daily change from prev_close
    and does NOT write back to the price cache. Used when loading cached ticks
    on startup where the stored change values are already correct.
    """
    if not _rdb:
        return tick

    price = tick["price"]
    ticker = tick["ticker"]

    perf_data = await _rdb.hgetall(PERF_KEY.format(ticker))
    if perf_data:
        for perf_field, close_field in zip(PERF_FIELDS, CLOSE_FIELDS):
            ref_str = perf_data.get(close_field)
            if ref_str:
                ref = float(ref_str)
                if ref:
                    tick[perf_field] = round((price - ref) / ref * 100, 4)

    return tick


async def load_all_cached_ticks() -> dict[str, dict]:
    """Load all cached ticks from Redis and add perf data.

    Used on startup to pre-populate state.ticks so the dashboard
    has data even when the market is closed. The cached price/change
    values are preserved as-is (they reflect the last trading session).
    """
    if not _rdb:
        return {}

    ticks = {}
    async for key in _rdb.scan_iter(match="ticker:prices:*"):
        ticker = key.removeprefix("ticker:prices:")
        tick = await get_cached_tick(ticker)
        if tick and tick["price"] > 0:
            tick = await add_perf_fields(tick)
            ticks[ticker] = tick

    logger.info("loaded %d cached ticks from redis", len(ticks))
    return ticks


async def fetch_and_cache_ticker(ticker: str) -> dict | None:
    """Fetch latest data from Massive REST API for a single ticker, seed Redis,
    and return an enriched tick dict. Used when a user adds a new ticker and
    we don't have any cached data for it yet."""
    if not _rdb:
        return None

    api_key = os.environ.get("MASSIVE_API_KEY", "")
    if not api_key:
        logger.warning("MASSIVE_API_KEY not set, cannot fetch %s", ticker)
        return None

    loop = asyncio.get_event_loop()

    try:
        from massive import RESTClient
        client = RESTClient(api_key=api_key)

        # Fetch last 2 trading days to get price + prev close
        def _fetch_recent():
            today = date.today()
            start = today - timedelta(days=10)
            return client.get_aggs(ticker, 1, "day", start, today, limit=10)

        aggs = await loop.run_in_executor(None, _fetch_recent)
        if not aggs or len(aggs) < 1:
            logger.warning("no agg data for %s", ticker)
            return None

        price = aggs[-1].close
        volume = int(aggs[-1].volume or 0)
        timestamp = aggs[-1].timestamp or 0

        # prev_close = second-to-last trading day's close (baseline for daily change)
        prev_close = aggs[-2].close if len(aggs) >= 2 else None

        if prev_close:
            await _rdb.set(PREV_CLOSE_KEY.format(ticker), str(prev_close))

        change = (price - prev_close) if prev_close else 0
        change_pct = (change / prev_close * 100) if prev_close else 0

        # Write price cache
        await _rdb.hset(PRICE_KEY.format(ticker), mapping={
            "price": str(price),
            "change": str(round(change, 4)),
            "changePct": str(round(change_pct, 4)),
            "volume": str(volume),
            "timestamp": str(timestamp),
        })

        # Fetch perf reference closes using shared trading calendar
        ref_dates = await loop.run_in_executor(None, trading_dates)

        perf_data: dict[str, str] = {}
        for label, ref_date in ref_dates.items():
            def _fetch_close(d=ref_date):
                r = client.get_aggs(ticker, 1, "day", d, d, limit=1)
                return r[0].close if r else None
            close = await loop.run_in_executor(None, _fetch_close)
            if close is not None:
                perf_data[label] = str(close)

        if perf_data:
            await _rdb.hset(PERF_KEY.format(ticker), mapping=perf_data)

        # Build enriched tick
        tick = {
            "ticker": ticker,
            "price": price,
            "change": round(change, 4),
            "changePct": round(change_pct, 4),
            "volume": volume,
            "timestamp": timestamp,
        }
        tick = await add_perf_fields(tick)

        logger.info("fetched and cached %s: price=%s change=%+.2f", ticker, price, change)
        return tick

    except Exception as e:
        logger.error("failed to fetch %s: %s", ticker, e)
        return None
