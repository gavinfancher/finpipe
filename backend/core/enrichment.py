"""
Tick enrichment using Redis-cached performance data.

Each ticker has a single Redis hash (ticker:{T}) with 20 fields:
  price, change, changePct, volume, timestamp, prevClose,
  perf5d..perf3y (7), ref5d..ref3y (7)

On live ticks: read prevClose + ref* fields, recompute, write back.
On cached load: HGETALL — everything is pre-computed, zero math needed.
"""

import asyncio
import logging
import os

import redis.asyncio as aioredis
from common.market import trading_dates
from common.redis_keys import (
    LABEL_TO_REF,
    PERF_FIELDS,
    REF_FIELDS,
    TICKER_KEY,
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
    """Enrich a live tick with change/perf data, write back to Redis."""
    if not _rdb:
        return tick

    price = tick["price"]
    ticker = tick["ticker"]
    key = TICKER_KEY.format(ticker)

    # Read prevClose + ref closes in one call
    data = await _rdb.hgetall(key)

    # Daily change vs prevClose
    prev_str = data.get("prevClose")
    if prev_str:
        prev = float(prev_str)
        change = price - prev
        tick["change"] = round(change, 4)
        tick["changePct"] = round(change / prev * 100, 4)
        tick["prevClose"] = prev

    # Perf % from reference closes
    for perf_field, ref_field in zip(PERF_FIELDS, REF_FIELDS):
        ref_str = data.get(ref_field)
        if ref_str:
            ref = float(ref_str)
            if ref:
                tick[perf_field] = round((price - ref) / ref * 100, 4)

    # Write everything back as a single hash update
    mapping = {
        "price": str(price),
        "change": str(tick.get("change", 0)),
        "changePct": str(tick.get("changePct", 0)),
        "volume": str(tick.get("volume", 0)),
        "timestamp": str(tick.get("timestamp", 0)),
    }
    for perf_field in PERF_FIELDS:
        if perf_field in tick:
            mapping[perf_field] = str(tick[perf_field])

    await _rdb.hset(key, mapping=mapping)

    return tick


async def get_cached_tick(ticker: str) -> dict | None:
    """Load a fully pre-computed tick from Redis. No math needed."""
    if not _rdb:
        return None
    data = await _rdb.hgetall(TICKER_KEY.format(ticker))
    if not data or "price" not in data:
        return None

    tick = {
        "ticker": ticker,
        "price": float(data["price"]),
        "change": float(data.get("change", 0)),
        "changePct": float(data.get("changePct", 0)),
        "volume": int(float(data.get("volume", 0))),
        "timestamp": int(float(data.get("timestamp", 0))),
    }

    prev_str = data.get("prevClose")
    if prev_str is not None:
        tick["prevClose"] = float(prev_str)

    # Perf fields are already computed — just read them
    for perf_field in PERF_FIELDS:
        val = data.get(perf_field)
        if val is not None:
            tick[perf_field] = float(val)

    return tick


async def load_all_cached_ticks() -> dict[str, dict]:
    """Load all cached ticks from Redis. Pre-computed, no math needed."""
    if not _rdb:
        return {}

    ticks = {}
    async for key in _rdb.scan_iter(match="ticker:*"):
        # Skip non-ticker keys (assignments, control)
        parts = key.split(":")
        if len(parts) != 2 or parts[0] != "ticker":
            continue
        ticker = parts[1]
        tick = await get_cached_tick(ticker)
        if tick and tick["price"] > 0:
            ticks[ticker] = tick

    logger.info("loaded %d cached ticks from redis", len(ticks))
    return ticks


async def fetch_and_cache_ticker(ticker: str) -> dict | None:
    """Fetch latest data from Massive REST API for a single ticker, seed Redis,
    and return a fully enriched tick dict. Used when a user adds a new ticker."""
    if not _rdb:
        return None

    api_key = os.environ.get("MASSIVE_API_KEY", "")
    if not api_key:
        logger.warning("MASSIVE_API_KEY not set, cannot fetch %s", ticker)
        return None

    loop = asyncio.get_event_loop()

    try:
        from datetime import date, timedelta

        from massive import RESTClient
        client = RESTClient(api_key=api_key)

        # Fetch last 10 days of aggs
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
        prev_close = aggs[-2].close if len(aggs) >= 2 else None

        # Fetch perf reference closes
        ref_dates = await loop.run_in_executor(None, trading_dates)

        from common.market import fetch_close

        mapping: dict[str, str] = {
            "price": str(price),
            "volume": str(volume),
            "timestamp": str(timestamp),
        }

        # prev_close + daily change
        if prev_close:
            mapping["prevClose"] = str(prev_close)
            change = price - prev_close
            change_pct = change / prev_close * 100
            mapping["change"] = str(round(change, 4))
            mapping["changePct"] = str(round(change_pct, 4))

        # Perf reference closes + computed percentages
        for label, ref_field in LABEL_TO_REF.items():
            ref_date = ref_dates.get(label)
            if ref_date:
                def _fetch_close(d=ref_date):
                    return fetch_close(client, ticker, d)
                close = await loop.run_in_executor(None, _fetch_close)
                if close is not None:
                    mapping[ref_field] = str(close)
                    perf_pct = (price - close) / close * 100
                    # ref5d -> perf5d
                    perf_field = ref_field.replace("ref", "perf")
                    mapping[perf_field] = str(round(perf_pct, 4))

        # Write single hash
        key = TICKER_KEY.format(ticker)
        await _rdb.hset(key, mapping=mapping)

        # Build tick dict for return
        tick = {
            "ticker": ticker,
            "price": price,
            "change": round(float(mapping.get("change", 0)), 4),
            "changePct": round(float(mapping.get("changePct", 0)), 4),
            "volume": volume,
            "timestamp": timestamp,
        }
        if "prevClose" in mapping:
            tick["prevClose"] = float(mapping["prevClose"])
        for perf_field in PERF_FIELDS:
            if perf_field in mapping:
                tick[perf_field] = float(mapping[perf_field])

        logger.info("fetched and cached %s: price=%s change=%+.2f", ticker, price, tick["change"])
        return tick

    except Exception as e:
        logger.error("failed to fetch %s: %s", ticker, e)
        return None
