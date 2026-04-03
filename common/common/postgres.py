"""
Shared PostgreSQL queries used by backend and dagster.
"""

ALL_TICKERS_QUERY = """
    select distinct ticker from user_tickers
    union
    select distinct ticker from positions
    order by ticker
"""


async def get_all_tickers(conn) -> list[str]:
    """Get all unique tickers across all users (watchlists + positions).

    Accepts any object with a .fetch() method (asyncpg.Connection or asyncpg.Pool).
    """
    rows = await conn.fetch(ALL_TICKERS_QUERY)
    return [r["ticker"] for r in rows]
