"""
Close-of-day job: fetches final closes from Massive REST API and updates
the single ticker:{T} Redis hash with reference closes, perf %, and price.

Runs daily after market close (scheduled for 20:30 NYC via Dagster).

Redis key written per ticker:
  ticker:{TICKER} — hash with 20 fields (price, change, prevClose, refs, perfs)

Usage:
    uv run dagster dev -f close_of_day.py
"""

import time
from datetime import date, timedelta

import pendulum
from common.market import PERF_LABELS, fetch_close, trading_dates
from common.postgres import get_all_tickers
from common.redis_keys import LABEL_TO_REF, TICKER_KEY
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
    """Fetch closes from Massive API and write to single Redis hash per ticker."""
    import os

    import redis

    log = get_dagster_logger()

    massive_key = os.environ.get("MASSIVE_API_KEY", "")
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

    client = RESTClient(api_key=massive_key)
    rdb = redis.from_url(redis_url, decode_responses=True)

    ref_dates = {k: date.fromisoformat(v) for k, v in ref_dates_raw.items()}

    success = 0
    for ticker in tickers:
        try:
            mapping: dict[str, str] = {}

            # Previous close
            prev_close = None
            prev_date = ref_dates.get("prev")
            if prev_date:
                prev_close = fetch_close(client, ticker, prev_date)
                if prev_close is not None:
                    mapping["prevClose"] = str(prev_close)

            # Reference closes
            ref_closes: dict[str, float] = {}
            for label in PERF_LABELS:
                ref_date = ref_dates.get(label)
                if ref_date:
                    close = fetch_close(client, ticker, ref_date)
                    if close is not None:
                        ref_field = LABEL_TO_REF[label]
                        mapping[ref_field] = str(close)
                        ref_closes[label] = close

            # Today's close as price (this runs at 20:30 after market close)
            today = pendulum.now("America/New_York").date()
            aggs = client.get_aggs(ticker, 1, "day", today - timedelta(days=5), today, limit=5)
            if aggs:
                price = aggs[-1].close
                volume = int(aggs[-1].volume or 0)
                timestamp = aggs[-1].timestamp or 0
                mapping["price"] = str(price)
                mapping["volume"] = str(volume)
                mapping["timestamp"] = str(timestamp)

                if prev_close:
                    change = price - prev_close
                    mapping["change"] = str(round(change, 4))
                    mapping["changePct"] = str(round(change / prev_close * 100, 4))

                for label, ref_close in ref_closes.items():
                    ref_field = LABEL_TO_REF[label]
                    perf_field = ref_field.replace("ref", "perf")
                    mapping[perf_field] = str(round((price - ref_close) / ref_close * 100, 4))

            if mapping:
                rdb.hset(TICKER_KEY.format(ticker), mapping=mapping)

            success += 1
            log.info("cached %s: prev=%s, fields=%d", ticker, prev_date, len(mapping))

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
