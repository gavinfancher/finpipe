"""
FastAPI application — wires together routes and pipeline lifecycle.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

import server.db as db
from server.logging_config import configure_logging
from server.pipeline import relay
from server.pipeline.enrichment import load_prev_closes
from server.api.routes import auth, internal, positions, users, ws

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init()
    startup_tickers = await db.get_all_tickers()
    logger.info("startup: loaded %d tickers from db", len(startup_tickers))
    if startup_tickers:
        await load_prev_closes(startup_tickers)
    task = asyncio.create_task(relay.run(startup_tickers))
    yield
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
    await db.close()


app = FastAPI(lifespan=lifespan)

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

Instrumentator().instrument(app).expose(app, endpoint="/metrics")
