"""
One-off script to seed Redis with reference closes for all tickers.
Run this to populate perf data before the first close-of-day Dagster job.

Usage: uv run python -m server.seed_redis
"""

import asyncio
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import asyncpg
import pandas_market_calendars as mcal
import redis
from dotenv import load_dotenv
from massive import RESTClient

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed_redis")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:finpipe-local@localhost:5432/finpipe")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
MASSIVE_API_KEY = os.environ.get("MASSIVE_API_KEY", "")

PREV_CLOSE_KEY = "ticker:prev_close:{}"
PERF_KEY = "ticker:perf:{}"
PRICE_KEY = "ticker:prices:{}"

_PERF_PERIODS = {
    "5d": 10,
    "1m": 35,
    "3m": 100,
    "6m": 200,
    "1y": 370,
    "ytd": None,
    "3y": 1100,
}


def trading_dates() -> dict[str, date]:
    nyse = mcal.get_calendar("NYSE")
    today = date.today()
    start = today - timedelta(days=1200)
    schedule = nyse.schedule(start_date=start, end_date=today)
    days = [d.date() for d in schedule.index]
    if not days:
        return {}

    result: dict[str, date] = {}

    # "prev" = second-to-last trading day (the close the last day's change is vs)
    # "last" = last trading day (the most recent regular-session close)
    if len(days) >= 2:
        result["prev"] = days[-2]
        result["last"] = days[-1]
    elif len(days) == 1:
        result["last"] = days[-1]

    for label, lookback in _PERF_PERIODS.items():
        if label == "ytd":
            year_start = date(today.year, 1, 1)
            ytd_days = [d for d in days if d >= year_start]
            if ytd_days:
                result["ytd"] = ytd_days[0]
        else:
            target = today - timedelta(days=lookback)
            candidates = [d for d in days if d >= target]
            if candidates:
                result[label] = candidates[0]
    return result


def fetch_close(client: RESTClient, ticker: str, d: date) -> float | None:
    try:
        aggs = client.get_aggs(ticker=ticker, multiplier=1, timespan="day", from_=d, to=d, limit=1)
        if aggs and len(aggs) > 0:
            return aggs[0].close
    except Exception as e:
        log.warning("failed %s on %s: %s", ticker, d, e)
    return None


async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("""
        select distinct ticker from user_tickers
        union
        select distinct ticker from positions
        order by ticker
    """)
    tickers = [r["ticker"] for r in rows]
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
        for label in _PERF_PERIODS:
            ref_date = ref_dates.get(label)
            if ref_date:
                close = fetch_close(client, ticker, ref_date)
                if close is not None:
                    perf_data[label] = str(close)
                    log.info("%s %s (%s) = %s", ticker, label, ref_date, close)

        if perf_data:
            rdb.hset(PERF_KEY.format(ticker), mapping=perf_data)

        # Price snapshot — use the snapshot endpoint for the most recent quote
        # (includes after-hours). Change is vs prev_close (second-to-last day).
        try:
            snap = client.get_snapshot_ticker("stocks", ticker)
            if snap and snap.prev_day and snap.prev_day.close:
                price = snap.prev_day.close
                volume = int(snap.prev_day.volume or 0)
                timestamp = snap.prev_day.timestamp or 0
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
