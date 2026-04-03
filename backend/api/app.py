"""
FastAPI application — serves REST API and WebSocket relay.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

import core.db as db
from core.logging_config import configure_logging
from streaming import relay
from core.enrichment import init_redis, close_redis, load_all_cached_ticks
from api.external import auth, positions, tickers, ws
from api.internal import health

configure_logging()
logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
ENABLE_RELAY = os.environ.get("ENABLE_RELAY", "true").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init()
    await init_redis(REDIS_URL)
    logger.info("startup: db and redis initialized")

    relay_task = None
    if ENABLE_RELAY:
        from core import state
        state.ticks = await load_all_cached_ticks()
        relay_task = asyncio.create_task(relay.run())
        logger.info("startup: relay enabled")
    else:
        logger.info("startup: relay disabled (ENABLE_RELAY=false)")

    yield

    if relay_task:
        relay_task.cancel()
        try:
            await relay_task
        except (asyncio.CancelledError, Exception):
            pass
    await close_redis()
    await db.close()


app = FastAPI(lifespan=lifespan)

from api.external.auth import limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/external")
app.include_router(tickers.router, prefix="/external")
app.include_router(positions.router, prefix="/external")
app.include_router(ws.router)
app.include_router(health.router, prefix="/internal")


@app.get("/external/health")
async def health():
    return {"status": "ok"}
