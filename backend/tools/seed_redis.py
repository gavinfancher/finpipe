"""
One-off script to seed Redis with reference closes for all tickers.
Run this to populate perf data before the first close-of-day Dagster job.

Usage: uv run python -m tools.seed_redis
"""

import asyncio
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import asyncpg
import redis
from common.market import PERF_LABELS, fetch_close, trading_dates
from common.postgres import get_all_tickers
from common.redis_keys import LABEL_TO_REF, TICKER_KEY
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
        mapping: dict[str, str] = {}

        # prev_close
        prev_close = None
        prev_date = ref_dates.get("prev")
        if prev_date:
            prev_close = fetch_close(client, ticker, prev_date)
            if prev_close is not None:
                mapping["prevClose"] = str(prev_close)
                log.info("%s prevClose (%s) = %s", ticker, prev_date, prev_close)

        # Perf reference closes + computed percentages
        # (price not known yet — will compute after fetching last agg)
        ref_closes: dict[str, float] = {}
        for label in PERF_LABELS:
            ref_date = ref_dates.get(label)
            if ref_date:
                close = fetch_close(client, ticker, ref_date)
                if close is not None:
                    ref_field = LABEL_TO_REF[label]
                    mapping[ref_field] = str(close)
                    ref_closes[label] = close
                    log.info("%s %s (%s) = %s", ticker, label, ref_date, close)

        # Price — last trading day's agg
        try:
            today = date.today()
            aggs = client.get_aggs(ticker, 1, "day", today - timedelta(days=10), today, limit=10)
            if aggs and len(aggs) >= 1:
                last_agg = aggs[-1]
                price = last_agg.close
                volume = int(last_agg.volume or 0)
                timestamp = last_agg.timestamp or 0

                mapping["price"] = str(price)
                mapping["volume"] = str(volume)
                mapping["timestamp"] = str(timestamp)

                # Daily change
                if prev_close:
                    change = price - prev_close
                    change_pct = change / prev_close * 100
                    mapping["change"] = str(round(change, 4))
                    mapping["changePct"] = str(round(change_pct, 4))
                    log.info("%s price=%s change=%+.2f (%+.2f%%)",
                             ticker, price, change, change_pct)

                # Compute perf percentages
                for label, ref_close in ref_closes.items():
                    ref_field = LABEL_TO_REF[label]
                    perf_field = ref_field.replace("ref", "perf")
                    perf_pct = (price - ref_close) / ref_close * 100
                    mapping[perf_field] = str(round(perf_pct, 4))

        except Exception as e:
            log.warning("failed price fetch for %s: %s", ticker, e)

        # Write single hash
        if mapping:
            rdb.hset(TICKER_KEY.format(ticker), mapping=mapping)

    log.info("done — seeded %d tickers", len(tickers))


if __name__ == "__main__":
    asyncio.run(main())
