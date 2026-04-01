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

import db
from logging_config import configure_logging
from pipeline import relay
from pipeline.enrichment import init_redis, close_redis, load_all_cached_ticks
from api.routes import auth, internal, positions, users, ws

configure_logging()
logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init()
    await init_redis(REDIS_URL)
    logger.info("startup: db and redis initialized")

    # Pre-load cached ticks so dashboard has data even when market is closed
    from pipeline import state
    state.ticks = await load_all_cached_ticks()

    relay_task = asyncio.create_task(relay.run())

    yield

    relay_task.cancel()
    try:
        await relay_task
    except (asyncio.CancelledError, Exception):
        pass
    await close_redis()
    await db.close()


app = FastAPI(lifespan=lifespan)

from api.routes.auth import limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/external")
app.include_router(users.router, prefix="/external")
app.include_router(positions.router, prefix="/external")
app.include_router(ws.router)
app.include_router(internal.router, prefix="/internal")


@app.get("/external/health")
async def health():
    return {"status": "ok"}
