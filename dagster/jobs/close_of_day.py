"""
Close-of-day job: fetches final closes from Massive REST API and writes
reference prices to Redis for next-day tick enrichment.

Runs daily after market close (scheduled for 20:30 NYC via Dagster).

Redis keys written:
  - ticker:prev_close:{TICKER}  — float, previous trading day close
  - ticker:perf:{TICKER}        — hash with 5d, 1m, 3m, 6m, 1y, ytd, 3y reference closes

Usage:
    uv run dagster dev -f close_of_day.py
"""

import time
from datetime import date, timedelta

import pendulum
from common.market import PERF_PERIODS, fetch_close, trading_dates
from common.postgres import get_all_tickers
from common.redis_keys import PERF_KEY, PREV_CLOSE_KEY
from dagster import (
    Out,
    ScheduleDefinition,
    get_dagster_logger,
    graph,
    op,
)
from massive import RESTClient


@op(out=Out(list))
def get_tickers_op():
    """Get all unique tickers from PostgreSQL."""
    import asyncio
    import os

    import asyncpg

    log = get_dagster_logger()
    database_url = os.environ["DATABASE_URL"]

    async def _fetch():
        conn = await asyncpg.connect(database_url)
        try:
            return await get_all_tickers(conn)
        finally:
            await conn.close()

    tickers = asyncio.run(_fetch())
    log.info("found %d tickers", len(tickers))
    return tickers


@op
def compute_reference_dates() -> dict:
    """Compute trading reference dates for perf calculations."""
    log = get_dagster_logger()
    ref = trading_dates()
    log.info("reference dates: %s", {k: str(v) for k, v in ref.items()})
    return {k: v.isoformat() for k, v in ref.items()}


@op
def fetch_and_cache_closes(tickers: list, ref_dates_raw: dict):
    """Fetch closes from Massive API and write to Redis."""
    import os

    import redis

    log = get_dagster_logger()

    massive_key = os.environ.get("MASSIVE_API_KEY", "")
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

    client = RESTClient(api_key=massive_key)
    rdb = redis.from_url(redis_url, decode_responses=True)

    # Convert ISO strings back to date objects
    ref_dates = {k: date.fromisoformat(v) for k, v in ref_dates_raw.items()}

    success = 0
    for ticker in tickers:
        try:
            # Previous close
            prev_date = ref_dates.get("prev")
            if prev_date:
                prev_close = fetch_close(client, ticker, prev_date)
                if prev_close is not None:
                    rdb.set(PREV_CLOSE_KEY.format(ticker), str(prev_close))

            # Perf reference closes
            perf_data: dict[str, str] = {}
            for label in PERF_PERIODS:
                ref_date = ref_dates.get(label)
                if ref_date:
                    close = fetch_close(client, ticker, ref_date)
                    if close is not None:
                        perf_data[label] = str(close)

            if perf_data:
                rdb.hset(PERF_KEY.format(ticker), mapping=perf_data)

            success += 1
            log.info("cached %s: prev=%s, perf_fields=%d", ticker, prev_date, len(perf_data))

            # Rate limit: ~5 req/sec to be safe
            time.sleep(0.2)

        except Exception as e:
            log.error("failed to process %s: %s", ticker, e)

    log.info("close-of-day complete: %d/%d tickers updated", success, len(tickers))


@graph
def close_of_day_graph():
    tickers = get_tickers_op()
    ref_dates = compute_reference_dates()
    fetch_and_cache_closes(tickers=tickers, ref_dates_raw=ref_dates)


close_of_day_job = close_of_day_graph.to_job(name="close_of_day_job")

close_of_day_schedule = ScheduleDefinition(
    job=close_of_day_job,
    cron_schedule="30 20 * * 1-5",  # 20:30 NYC, weekdays
    execution_timezone="America/New_York",
)