"""
Trading calendar utilities, market status, and Massive API helpers.
"""

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
from dateutil.relativedelta import relativedelta
from massive import RESTClient

logger = logging.getLogger(__name__)

NY = ZoneInfo("America/New_York")
_nyse = mcal.get_calendar("NYSE")

# Performance period labels — used as Redis hash field names
PERF_LABELS = ("5d", "1m", "3m", "6m", "1y", "ytd", "3y")


def trading_dates() -> dict[str, date]:
    """Compute reference trading dates for perf calculations.

    Industry-standard convention (matches Fidelity/Bloomberg): calendar offsets
    from the last trading day, resolved to the last trading day on or before
    the target date.

    Returns a dict with keys: 'prev', '5d', '1m', '3m', '6m', '1y', 'ytd', '3y'
    mapped to the appropriate NYSE trading date.
    """
    today = datetime.now(NY).date()
    start = today - timedelta(days=1200)
    schedule = _nyse.schedule(start_date=start, end_date=today)
    days = [d.date() for d in schedule.index]

    if len(days) < 2:
        return {}

    result: dict[str, date] = {}
    last = days[-1]  # most recent trading day

    # prev_close baseline: n-2 so that on weekends/holidays,
    # daily change reflects the last session's move
    result["prev"] = days[-2]

    # Calendar offsets from the last trading day, resolved to last
    # trading day on or before the target date
    targets = {
        "5d": last - timedelta(days=5),
        "1m": last - relativedelta(months=1),
        "3m": last - relativedelta(months=3),
        "6m": last - relativedelta(months=6),
        "1y": last - relativedelta(years=1),
        "3y": last - relativedelta(years=3),
    }

    for label, target in targets.items():
        candidates = [d for d in days if d <= target]
        if candidates:
            result[label] = candidates[-1]

    # YTD: last trading day of the previous year
    prev_year_end = date(today.year - 1, 12, 31)
    ytd_candidates = [d for d in days if d <= prev_year_end]
    if ytd_candidates:
        result["ytd"] = ytd_candidates[-1]

    return result


def _next_trading_day(from_date: date) -> date:
    """Find the next NYSE trading day on or after from_date."""
    search_end = from_date + timedelta(days=10)
    schedule = _nyse.schedule(start_date=from_date, end_date=search_end)
    if len(schedule) > 0:
        return schedule.index[0].date()
    return from_date


def get_market_status() -> dict:
    """Compute current market session and timing info.

    Returns dict with:
      session: "pre-market" | "open" | "post-market" | "closed"
      is_holiday: bool
      holiday_name: str | None
      next_open: int (unix timestamp — next pre-market open, 4am NY)
      next_close: int (unix timestamp — post-market end, 8pm NY or early close + 3h)
    """
    now = datetime.now(NY)
    today = now.date()
    mins = now.hour * 60 + now.minute

    # Check if today is a trading day
    schedule = _nyse.schedule(start_date=today, end_date=today)
    is_trading_day = len(schedule) > 0

    # Holiday detection: weekday but not a trading day
    is_holiday = False
    holiday_name = None
    if not is_trading_day and today.weekday() < 5:
        is_holiday = True
        holiday_name = _get_holiday_name(today)

    # Determine session
    if not is_trading_day:
        session = "closed"
    elif mins < 4 * 60:
        session = "closed"
    elif mins < 9 * 60 + 30:
        session = "pre-market"
    elif mins < 16 * 60:
        session = "open"
    else:
        # Check for early close
        post_end_mins = 20 * 60  # default 8pm
        if len(schedule) > 0:
            market_close = schedule.iloc[0]["market_close"].astimezone(NY)
            regular_close_mins = market_close.hour * 60 + market_close.minute
            if regular_close_mins < 16 * 60:
                # Early close day — post-market ends 3h after regular close
                post_end_mins = regular_close_mins + 3 * 60

        if mins < post_end_mins:
            session = "post-market"
        else:
            session = "closed"

    # Also check early close affecting open→post-market boundary
    if is_trading_day and session == "open" and len(schedule) > 0:
        market_close = schedule.iloc[0]["market_close"].astimezone(NY)
        regular_close_mins = market_close.hour * 60 + market_close.minute
        if regular_close_mins < 16 * 60 and mins >= regular_close_mins:
            session = "post-market"

    # Compute next_open: 4am NY on next trading day
    if session == "closed":
        if mins < 4 * 60 and is_trading_day:
            # Before 4am on a trading day — opens today
            next_open_day = today
        else:
            next_open_day = _next_trading_day(today + timedelta(days=1))
    else:
        # Currently in a session — next open is the next trading day
        next_open_day = _next_trading_day(today + timedelta(days=1))

    next_open_dt = datetime.combine(next_open_day, time(4, 0), tzinfo=NY)
    next_open = int(next_open_dt.timestamp())

    # Compute next_close: post-market end (8pm NY or early close + 3h)
    if session in ("pre-market", "open", "post-market"):
        close_day = today
    else:
        close_day = _next_trading_day(
            today + timedelta(days=1) if mins >= 4 * 60 or not is_trading_day
            else today
        )

    close_hour, close_minute = 20, 0  # default 8pm
    day_schedule = _nyse.schedule(start_date=close_day, end_date=close_day)
    if len(day_schedule) > 0:
        mc = day_schedule.iloc[0]["market_close"].astimezone(NY)
        if mc.hour < 16:
            # Early close — post-market ends 3h after
            close_hour = mc.hour + 3
            close_minute = mc.minute

    next_close_dt = datetime.combine(
        close_day, time(close_hour, close_minute), tzinfo=NY
    )
    next_close = int(next_close_dt.timestamp())

    return {
        "session": session,
        "is_holiday": is_holiday,
        "holiday_name": holiday_name,
        "next_open": next_open,
        "next_close": next_close,
    }


def _get_holiday_name(d: date) -> str | None:
    """Try to resolve NYSE holiday name for a date."""
    try:
        holidays = _nyse.holidays()
        if hasattr(holidays, "holidays"):
            import pandas as pd
            ts = pd.Timestamp(d)
            if ts in holidays.holidays:
                return "Market Holiday"
    except Exception:
        pass
    return "Market Holiday"


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


def derive_close_of_day_perf_fields(
    price: float,
    prev_close: float | None,
    ref_closes: dict[str, float],
    label_to_ref: dict[str, str],
) -> dict[str, str]:
    """Compute change and perf* hash fields from today's close and reference closes.

    ``ref_closes`` keys are period labels (e.g. ``5d``, ``1m``) matching
    ``label_to_ref`` (e.g. common.redis_keys.LABEL_TO_REF).
    """
    out: dict[str, str] = {}
    if prev_close is not None:
        change = price - prev_close
        out["change"] = str(round(change, 4))
        out["changePct"] = str(round(change / prev_close * 100, 4))
    for label, ref_close in ref_closes.items():
        ref_field = label_to_ref[label]
        perf_field = ref_field.replace("ref", "perf")
        out[perf_field] = str(round((price - ref_close) / ref_close * 100, 4))
    return out
