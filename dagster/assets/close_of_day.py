"""
Close-of-day market data: reference closes from Massive, then Redis ticker hashes.

Scheduled via ``close_of_day_job`` (weekdays 20:30 America/New_York).
"""

import asyncio
import time
from datetime import timedelta

import pendulum
from dagster import AssetExecutionContext, MetadataValue, asset

from common.market import (
    PERF_LABELS,
    derive_close_of_day_perf_fields,
    fetch_close,
    trading_dates,
)
from common.redis_keys import LABEL_TO_REF, TICKER_KEY
from resources.massive_api import MassiveAPIResource
from resources.postgres import PostgresResource
from resources.redis import RedisResource


@asset(
    name="reference_closes",
    group_name="market_data",
    compute_kind="python",
)
def reference_closes(
    context: AssetExecutionContext,
    postgres: PostgresResource,
    massive_api: MassiveAPIResource,
) -> dict:
    """Fetch per-ticker reference closes and latest daily bar from Massive."""
    tickers = asyncio.run(postgres.fetch_all_tickers())
    context.log.info("found %d tickers", len(tickers))

    ref_dates = trading_dates()
    context.log.info("reference dates: %s", {k: str(v) for k, v in ref_dates.items()})

    client = massive_api.get_client()
    today = pendulum.now("America/New_York").date()
    rows: list[dict] = []

    for ticker in tickers:
        row: dict = {
            "ticker": ticker,
            "base_mapping": {},
            "ref_closes": {},
            "prev_close": None,
            "price_float": None,
        }
        try:
            mapping: dict[str, str] = {}
            prev_close = None
            prev_date = ref_dates.get("prev")
            if prev_date:
                prev_close = fetch_close(client, ticker, prev_date)
                if prev_close is not None:
                    mapping["prevClose"] = str(prev_close)

            ref_closes: dict[str, float] = {}
            for label in PERF_LABELS:
                ref_date = ref_dates.get(label)
                if ref_date:
                    close = fetch_close(client, ticker, ref_date)
                    if close is not None:
                        ref_field = LABEL_TO_REF[label]
                        mapping[ref_field] = str(close)
                        ref_closes[label] = close

            aggs = client.get_aggs(
                ticker, 1, "day", today - timedelta(days=5), today, limit=5
            )
            price = None
            if aggs:
                price = aggs[-1].close
                volume = int(aggs[-1].volume or 0)
                timestamp = aggs[-1].timestamp or 0
                mapping["price"] = str(price)
                mapping["volume"] = str(volume)
                mapping["timestamp"] = str(timestamp)

            row["base_mapping"] = mapping
            row["ref_closes"] = ref_closes
            row["prev_close"] = prev_close
            row["price_float"] = price
            rows.append(row)
            context.log.info(
                "fetched %s: prev=%s, fields=%d",
                ticker,
                prev_date,
                len(mapping),
            )
            time.sleep(0.2)
        except Exception as e:
            context.log.error("failed to process %s: %s", ticker, e)
            rows.append(row)

    context.add_output_metadata({"ticker_count": MetadataValue.int(len(rows))})
    return {"rows": rows}


@asset(
    name="ticker_cache",
    group_name="market_data",
    compute_kind="redis",
)
def ticker_cache(
    context: AssetExecutionContext,
    reference_closes: dict,
    redis: RedisResource,
) -> None:
    """Merge perf fields and write ``ticker:{TICKER}`` hashes to Redis."""
    r = redis.get_client()
    success = 0
    for row in reference_closes["rows"]:
        ticker = row["ticker"]
        base = dict(row.get("base_mapping") or {})
        price = row.get("price_float")
        prev_close = row.get("prev_close")
        ref_closes = row.get("ref_closes") or {}

        if price is not None:
            base.update(
                derive_close_of_day_perf_fields(
                    price, prev_close, ref_closes, LABEL_TO_REF
                )
            )

        if base:
            r.hset(TICKER_KEY.format(ticker), mapping=base)
            success += 1
            context.log.info("cached %s: fields=%d", ticker, len(base))

    context.log.info("close-of-day cache: %d tickers updated", success)
