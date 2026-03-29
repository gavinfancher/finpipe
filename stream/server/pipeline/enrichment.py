"""
Previous day close fetching and tick enrichment.
"""

import asyncio
import bisect
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx
import pandas as pd
import pandas_market_calendars as mcal

from server.config import MASSIVE_API_KEY
from server.pipeline import state

logger = logging.getLogger(__name__)

_http = httpx.AsyncClient(
    base_url="https://api.massive.com",
    headers={"Authorization": f"Bearer {MASSIVE_API_KEY}"},
    timeout=10.0,
)

_cal = mcal.get_calendar("NYSE")

_PERIODS = ("prev", "5d", "1m", "3m", "6m", "1y", "ytd", "3y")


@dataclass
class TradingDates:
    prev: date
    d5: date
    m1: date
    m3: date
    m6: date
    y1: date
    ytd: date
    y3: date


def _trading_dates() -> TradingDates:
    """Return key historical trading dates using the NYSE calendar."""
    today = date.today()
    start = (pd.Timestamp.today() - pd.DateOffset(years=3, months=1)).date()
    schedule = _cal.schedule(start_date=str(start), end_date=str(today))
    trading_days = schedule.index.normalize().date.tolist()
    completed = [d for d in trading_days if d < today]

    def last_on_or_before(target: date) -> date:
        idx = bisect.bisect_right(completed, target) - 1
        return completed[max(idx, 0)]

    def first_on_or_after(target: date) -> date:
        idx = bisect.bisect_left(completed, target)
        return completed[min(idx, len(completed) - 1)]

    now = pd.Timestamp.today()
    return TradingDates(
        prev=completed[-1],
        d5=completed[-6] if len(completed) >= 6 else completed[0],
        ytd=first_on_or_after(date(today.year, 1, 1)),
        m1=last_on_or_before((now - pd.DateOffset(months=1)).date()),
        m3=last_on_or_before((now - pd.DateOffset(months=3)).date()),
        m6=last_on_or_before((now - pd.DateOffset(months=6)).date()),
        y1=last_on_or_before((now - pd.DateOffset(years=1)).date()),
        y3=last_on_or_before((now - pd.DateOffset(years=3)).date()),
    )


async def _fetch_closes(ticker: str, dates: TradingDates) -> dict[str, float | None]:
    """Fetch daily bars covering all reference dates.
    Returns dict keyed by period: prev, 5d, 1m, 3m, 6m, 1y, ytd, 3y.
    """
    empty: dict[str, float | None] = {k: None for k in _PERIODS}
    try:
        r = await _http.get(
            f"/v2/aggs/ticker/{ticker}/range/1/day/{dates.y3}/{dates.prev}",
            params={"adjusted": "true", "sort": "asc", "limit": 1000},
        )
        r.raise_for_status()
        results = r.json().get("results") or []
        if not results:
            return empty
        bars_by_date = {
            datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc).date(): b["c"]
            for b in results
        }
        return {
            "prev": bars_by_date.get(dates.prev),
            "5d":   bars_by_date.get(dates.d5),
            "1m":   bars_by_date.get(dates.m1),
            "3m":   bars_by_date.get(dates.m3),
            "6m":   bars_by_date.get(dates.m6),
            "1y":   bars_by_date.get(dates.y1),
            "ytd":  bars_by_date.get(dates.ytd),
            "3y":   bars_by_date.get(dates.y3),
        }
    except Exception as e:
        logger.warning("closes fetch failed for %s: %s", ticker, e)
    return empty


_STATE_MAP = [
    ("5d",  "closes_5d"),
    ("1m",  "closes_1m"),
    ("3m",  "closes_3m"),
    ("6m",  "closes_6m"),
    ("1y",  "closes_1y"),
    ("ytd", "closes_ytd"),
    ("3y",  "closes_3y"),
]


async def load_prev_closes(tickers: list[str]):
    dates = _trading_dates()
    logger.info(
        "fetching closes: prev=%s 5d=%s 1m=%s 3m=%s 6m=%s 1y=%s ytd=%s 3y=%s",
        dates.prev, dates.d5, dates.m1, dates.m3, dates.m6, dates.y1, dates.ytd, dates.y3,
    )
    results = await asyncio.gather(*[_fetch_closes(t, dates) for t in tickers])
    loaded = 0
    for ticker, closes in zip(tickers, results):
        if closes["prev"] is not None:
            state.prev_closes[ticker] = closes["prev"]
            loaded += 1
            logger.info("prev close: %s = %.4f", ticker, closes["prev"])
        else:
            logger.warning("prev close: %s = not found", ticker)
        for period, attr in _STATE_MAP:
            if closes[period] is not None:
                getattr(state, attr)[ticker] = closes[period]
    logger.info("prev closes loaded for %d/%d tickers", loaded, len(tickers))


_ENRICH_MAP = [
    ("perf5d",  "closes_5d"),
    ("perf1m",  "closes_1m"),
    ("perf3m",  "closes_3m"),
    ("perf6m",  "closes_6m"),
    ("perf1y",  "closes_1y"),
    ("perfYtd", "closes_ytd"),
    ("perf3y",  "closes_3y"),
]


def enrich_tick(tick: dict) -> dict:
    """Recalculate change/changePct/perf from reference closes."""
    price = tick["price"]
    ticker = tick["ticker"]

    prev = state.prev_closes.get(ticker)
    if prev:
        change = price - prev
        tick["change"] = round(change, 4)
        tick["changePct"] = round(change / prev * 100, 4)
        tick["prevClose"] = prev

    for field, attr in _ENRICH_MAP:
        ref = getattr(state, attr).get(ticker)
        if ref:
            tick[field] = round((price - ref) / ref * 100, 4)

    return tick
