"""
Stress test: 50 concurrent users each registering and updating their watchlist 20 times.
Run with: uv run python stress_users.py
"""

import asyncio
import random
import string
import httpx

BASE = "http://localhost:8080"
NUM_USERS = 50
WATCHLIST_ROUNDS = 20

TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "JPM", "V",
    "UNH", "XOM", "LLY", "JNJ", "WMT", "MA", "AVGO", "PG", "HD", "CVX",
    "MRK", "ABBV", "COST", "PEP", "KO", "ADBE", "CRM", "TMO", "ACN", "MCD",
    "BAC", "NFLX", "AMD", "LIN", "DHR", "TXN", "NEE", "PM", "ORCL", "AMGN",
    "INTC", "UPS", "RTX", "QCOM", "HON", "IBM", "GS", "CAT", "SPGI", "INTU",
]


def rand_suffix(n=6):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


async def run_user(client: httpx.AsyncClient, user_id: int):
    username = f"stressuser_{user_id}_{rand_suffix()}"
    password = "testpass123"

    # Register
    r = await client.post("/external/auth/register", json={"username": username, "password": password})
    if r.status_code != 200:
        print(f"[{username}] register failed: {r.status_code} {r.text}")
        return
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"[{username}] registered")

    # 20 rounds of watchlist changes
    current = set()
    for round_num in range(WATCHLIST_ROUNDS):
        pool = [t for t in TICKERS if t not in current]
        to_add = random.sample(pool, min(random.randint(1, 4), len(pool)))
        to_remove = random.sample(list(current), min(random.randint(0, 2), len(current)))

        r = await client.patch(
            "/external/tickers",
            json={"add": to_add, "remove": to_remove},
            headers=headers,
        )
        if r.status_code == 200:
            current.update(to_add)
            current.difference_update(to_remove)
            print(f"[{username}] round {round_num + 1:02d} +{to_add} -{to_remove} => {sorted(current)}")
        else:
            print(f"[{username}] patch failed round {round_num + 1}: {r.status_code} {r.text}")

        await asyncio.sleep(random.uniform(0.05, 0.3))

    print(f"[{username}] done — final watchlist: {sorted(current)}")


async def main():
    print(f"Starting stress test: {NUM_USERS} users x {WATCHLIST_ROUNDS} rounds")
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        await asyncio.gather(*[run_user(client, i) for i in range(NUM_USERS)])
    print("Stress test complete.")


if __name__ == "__main__":
    asyncio.run(main())
