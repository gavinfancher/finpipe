"""
Trading calendar utilities and Massive API helpers.
"""

import logging
from datetime import date, timedelta

import pandas_market_calendars as mcal
from massive import RESTClient

logger = logging.getLogger(__name__)

# Performance periods: label → approximate calendar days lookback
PERF_PERIODS: dict[str, int | None] = {
    "5d": 10,
    "1m": 35,
    "3m": 100,
    "6m": 200,
    "1y": 370,
    "ytd": None,
    "3y": 1100,
}


def trading_dates() -> dict[str, date]:
    """Compute reference trading dates for perf calculations.

    Returns a dict with keys: 'prev', '5d', '1m', '3m', '6m', '1y', 'ytd', '3y'
    mapped to the appropriate NYSE trading date.
    """
    nyse = mcal.get_calendar("NYSE")
    today = date.today()
    start = today - timedelta(days=1200)
    schedule = nyse.schedule(start_date=start, end_date=today)
    days = [d.date() for d in schedule.index]

    if not days:
        return {}

    result: dict[str, date] = {}
    result["prev"] = days[-1]

    for label, lookback in PERF_PERIODS.items():
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
        logger.warning("failed to fetch %s on %s: %s", ticker, d, e)
    return None
