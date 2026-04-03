"""
One-off script to seed Redis with reference closes for all tickers.
Run this to populate perf data before the first close-of-day Dagster job.

Usage: uv run python -m seed_redis
"""

import asyncio
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import asyncpg
import redis
from common.market import PERF_PERIODS, fetch_close, trading_dates
from common.postgres import get_all_tickers
from common.redis_keys import PERF_KEY, PREV_CLOSE_KEY, PRICE_KEY
from dotenv import load_dotenv
from massive import RESTClient

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed_redis")

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
MASSIVE_API_KEY = os.environ.get("MASSIVE_API_KEY", "")


async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    tickers = await get_all_tickers(conn)
    await conn.close()

    if not tickers:
        log.info("no tickers found")
        return

    log.info("tickers: %s", tickers)

    ref_dates = trading_dates()
    log.info("reference dates: %s", {k: str(v) for k, v in ref_dates.items()})

    client = RESTClient(api_key=MASSIVE_API_KEY)
    rdb = redis.from_url(REDIS_URL, decode_responses=True)

    for ticker in tickers:
        # prev_close = second-to-last trading day's close
        # This is what the last trading day's change is calculated against.
        prev_close = None
        prev_date = ref_dates.get("prev")
        if prev_date:
            prev_close = fetch_close(client, ticker, prev_date)
            if prev_close is not None:
                rdb.set(PREV_CLOSE_KEY.format(ticker), str(prev_close))
                log.info("%s prev_close (%s) = %s", ticker, prev_date, prev_close)

        # Perf reference closes
        perf_data: dict[str, str] = {}
        for label in PERF_PERIODS:
            ref_date = ref_dates.get(label)
            if ref_date:
                close = fetch_close(client, ticker, ref_date)
                if close is not None:
                    perf_data[label] = str(close)
                    log.info("%s %s (%s) = %s", ticker, label, ref_date, close)

        if perf_data:
            rdb.hset(PERF_KEY.format(ticker), mapping=perf_data)

        # Price snapshot — use the snapshot endpoint for the most recent quote
        # (includes after-hours). Change is vs prev_close (last trading day).
        try:
            snap = client.get_snapshot_ticker("stocks", ticker)
            if snap and snap.day and snap.day.close:
                price = snap.day.close
                volume = int(snap.day.volume or 0)
                timestamp = snap.day.timestamp or 0
                change = (price - prev_close) if prev_close else 0
                change_pct = (change / prev_close * 100) if prev_close else 0
                rdb.hset(PRICE_KEY.format(ticker), mapping={
                    "price": str(price),
                    "change": str(round(change, 4)),
                    "changePct": str(round(change_pct, 4)),
                    "volume": str(volume),
                    "timestamp": str(timestamp),
                })
                log.info("%s snapshot price=%s change=%+.2f (%+.2f%%)",
                         ticker, price, change, change_pct)
        except Exception as e:
            log.warning("failed snapshot for %s: %s", ticker, e)

    log.info("done — seeded %d tickers", len(tickers))


if __name__ == "__main__":
    asyncio.run(main())
