"""
Postgres helpers for per-user ticker persistence.
"""

import asyncpg

from server.config import DATABASE_URL

_pool: asyncpg.Pool | None = None


async def init():
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL)
    async with _pool.acquire() as conn:
        await conn.execute("""
            create table if not exists users (
                id       serial primary key,
                username varchar(32) unique not null
            )
        """)
        await conn.execute("""
            alter table users add column if not exists password_hash text
        """)
        await conn.execute("""
            alter table users add column if not exists api_key_hash text
        """)
        await conn.execute("""
            create table if not exists user_tickers (
                user_id integer not null references users(id) on delete cascade,
                ticker  varchar(10) not null,
                primary key (user_id, ticker)
            )
        """)
        await conn.execute("""
            create table if not exists positions (
                id         serial primary key,
                user_id    integer not null references users(id) on delete cascade,
                ticker     varchar(10) not null,
                shares     numeric not null,
                cost_basis numeric not null,
                opened_at  timestamptz not null default now()
            )
        """)
        await conn.execute("""
            alter table users add column if not exists preferences jsonb not null default '{}'
        """)
        await conn.execute("""
            alter table user_tickers add column if not exists sort_order integer not null default 0
        """)


async def close():
    if _pool:
        await _pool.close()




# --- auth ---

async def create_user(username: str, password_hash: str) -> bool:
    """Returns True if created, False if username already taken."""
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "insert into users (username, password_hash) values ($1, $2) on conflict (username) do nothing",
            username,
            password_hash,
        )
    return result == "INSERT 0 1"


async def get_or_create_user(username: str):
    async with _pool.acquire() as conn:
        await conn.execute(
            "insert into users (username) values ($1) on conflict (username) do nothing",
            username,
        )


async def store_api_key(username: str, key_hash: str):
    async with _pool.acquire() as conn:
        await conn.execute(
            "update users set api_key_hash = $1 where username = $2",
            key_hash,
            username,
        )


async def get_username_by_api_key(key_hash: str) -> str | None:
    async with _pool.acquire() as conn:
        return await conn.fetchval(
            "select username from users where api_key_hash = $1", key_hash
        )


async def get_password_hash(username: str) -> str | None:
    async with _pool.acquire() as conn:
        return await conn.fetchval(
            "select password_hash from users where username = $1", username
        )


# --- tickers ---

async def get_user_tickers(username: str) -> list[str]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            select t.ticker
            from user_tickers t
            join users u on u.id = t.user_id
            where u.username = $1
            order by t.sort_order, t.ticker
            """,
            username,
        )
    return [r["ticker"] for r in rows]


async def add_user_ticker(username: str, ticker: str) -> list[str]:
    async with _pool.acquire() as conn:
        user_id = await conn.fetchval(
            "select id from users where username = $1", username
        )
        if user_id is None:
            raise ValueError(f"user not found: {username}")
        await conn.execute(
            "insert into user_tickers (user_id, ticker) values ($1, $2) on conflict do nothing",
            user_id,
            ticker,
        )
    return await get_user_tickers(username)


async def remove_user_ticker(username: str, ticker: str) -> list[str]:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            delete from user_tickers t
            using users u
            where u.id = t.user_id and u.username = $1 and t.ticker = $2
            """,
            username,
            ticker,
        )
    return await get_user_tickers(username)


async def patch_user_tickers(username: str, add: list[str], remove: list[str]) -> list[str]:
    async with _pool.acquire() as conn:
        user_id = await conn.fetchval(
            "select id from users where username = $1", username
        )
        if add:
            await conn.executemany(
                "insert into user_tickers (user_id, ticker) values ($1, $2) on conflict do nothing",
                [(user_id, t) for t in add],
            )
        if remove:
            await conn.execute(
                "delete from user_tickers where user_id = $1 and ticker = any($2::varchar[])",
                user_id,
                remove,
            )
    return await get_user_tickers(username)


# --- positions ---

async def get_positions(username: str) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            select p.id, p.ticker, p.shares, p.cost_basis, p.opened_at
            from positions p
            join users u on u.id = p.user_id
            where u.username = $1
            order by p.opened_at
            """,
            username,
        )
    return [
        {
            "id": r["id"],
            "ticker": r["ticker"],
            "shares": float(r["shares"]),
            "cost_basis": float(r["cost_basis"]),
            "opened_at": r["opened_at"].isoformat(),
        }
        for r in rows
    ]


async def add_position(username: str, ticker: str, shares: float, cost_basis: float) -> dict:
    async with _pool.acquire() as conn:
        user_id = await conn.fetchval("select id from users where username = $1", username)
        if user_id is None:
            raise ValueError(f"user not found: {username}")
        row = await conn.fetchrow(
            """
            insert into positions (user_id, ticker, shares, cost_basis)
            values ($1, $2, $3, $4)
            returning id, ticker, shares, cost_basis, opened_at
            """,
            user_id, ticker, shares, cost_basis,
        )
    return {
        "id": row["id"],
        "ticker": row["ticker"],
        "shares": float(row["shares"]),
        "cost_basis": float(row["cost_basis"]),
        "opened_at": row["opened_at"].isoformat(),
    }


async def update_position(username: str, position_id: int, shares: float, cost_basis: float) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            update positions p
            set shares = $3, cost_basis = $4
            from users u
            where u.id = p.user_id and u.username = $1 and p.id = $2
            returning p.id, p.ticker, p.shares, p.cost_basis, p.opened_at
            """,
            username, position_id, shares, cost_basis,
        )
    if row is None:
        return None
    return {
        "id": row["id"],
        "ticker": row["ticker"],
        "shares": float(row["shares"]),
        "cost_basis": float(row["cost_basis"]),
        "opened_at": row["opened_at"].isoformat(),
    }


async def delete_position(username: str, position_id: int) -> bool:
    async with _pool.acquire() as conn:
        result = await conn.execute(
            """
            delete from positions p
            using users u
            where u.id = p.user_id and u.username = $1 and p.id = $2
            """,
            username, position_id,
        )
    return result == "DELETE 1"


# --- preferences ---

async def get_preferences(username: str) -> dict:
    async with _pool.acquire() as conn:
        row = await conn.fetchval(
            "select preferences from users where username = $1", username
        )
    import json
    return json.loads(row) if row else {}


async def set_preferences(username: str, prefs: dict):
    import json
    async with _pool.acquire() as conn:
        await conn.execute(
            "update users set preferences = $1::jsonb where username = $2",
            json.dumps(prefs), username,
        )


async def reorder_tickers(username: str, tickers: list[str]):
    """Set sort_order based on the provided list order."""
    async with _pool.acquire() as conn:
        user_id = await conn.fetchval(
            "select id from users where username = $1", username
        )
        if user_id is None:
            return
        for i, ticker in enumerate(tickers):
            await conn.execute(
                "update user_tickers set sort_order = $1 where user_id = $2 and ticker = $3",
                i, user_id, ticker,
            )


# --- startup ---

async def get_all_tickers() -> list[str]:
    """Union of watchlist and position tickers across all users — used for warm startup."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            select distinct ticker from user_tickers
            union
            select distinct ticker from positions
            order by ticker
            """
        )
    return [r["ticker"] for r in rows]
