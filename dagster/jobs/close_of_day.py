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

import pandas_market_calendars as mcal
import pendulum
from dagster import (
    Definitions,
    Out,
    ScheduleDefinition,
    get_dagster_logger,
    graph,
    op,
)
from massive import RESTClient

PREV_CLOSE_KEY = "ticker:prev_close:{}"
PERF_KEY = "ticker:perf:{}"

# Performance periods: label → approximate calendar days lookback
_PERF_PERIODS = {
    "5d": 10,
    "1m": 35,
    "3m": 100,
    "6m": 200,
    "1y": 370,
    "ytd": None,
    "3y": 1100,
}


def _trading_dates() -> dict[str, date]:
    """Compute reference trading dates for perf calculations."""
    nyse = mcal.get_calendar("NYSE")
    today = date.today()

    start = today - timedelta(days=1200)
    schedule = nyse.schedule(start_date=start, end_date=today)
    days = [d.date() for d in schedule.index]

    if not days:
        return {}

    result: dict[str, date] = {}
    result["prev"] = days[-1]

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


def _fetch_close(client: RESTClient, ticker: str, d: date) -> float | None:
    """Fetch closing price for a ticker on a specific date."""
    try:
        aggs = client.get_aggs(
            ticker=ticker,
            multiplier=1,
            timespan="day",
            from_=d,
            to=d,
            limit=1,
        )
        if aggs and len(aggs) > 0:
            return aggs[0].close
    except Exception as e:
        get_dagster_logger().warning("failed to fetch %s on %s: %s", ticker, d, e)
    return None


@op(out=Out(list))
def get_tickers():
    """Get all unique tickers from PostgreSQL."""
    import asyncio
    import os

    import asyncpg

    log = get_dagster_logger()
    database_url = os.environ["DATABASE_URL"]

    async def _fetch():
        conn = await asyncpg.connect(database_url)
        try:
            rows = await conn.fetch("""
                select distinct ticker from user_tickers
                union
                select distinct ticker from positions
                order by ticker
            """)
            return [r["ticker"] for r in rows]
        finally:
            await conn.close()

    tickers = asyncio.run(_fetch())
    log.info("found %d tickers", len(tickers))
    return tickers


@op
def compute_reference_dates() -> dict:
    """Compute trading reference dates for perf calculations."""
    log = get_dagster_logger()
    ref = _trading_dates()
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
                prev_close = _fetch_close(client, ticker, prev_date)
                if prev_close is not None:
                    rdb.set(PREV_CLOSE_KEY.format(ticker), str(prev_close))

            # Perf reference closes
            perf_data: dict[str, str] = {}
            for label in _PERF_PERIODS:
                ref_date = ref_dates.get(label)
                if ref_date:
                    close = _fetch_close(client, ticker, ref_date)
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
    tickers = get_tickers()
    ref_dates = compute_reference_dates()
    fetch_and_cache_closes(tickers=tickers, ref_dates_raw=ref_dates)


close_of_day_job = close_of_day_graph.to_job(name="close_of_day_job")

close_of_day_schedule = ScheduleDefinition(
    job=close_of_day_job,
    cron_schedule="30 20 * * 1-5",  # 20:30 NYC, weekdays
    execution_timezone="America/New_York",
)

defs = Definitions(
    jobs=[close_of_day_job],
    schedules=[close_of_day_schedule],
)
