import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import core.auth as auth
import core.db as db
from api.deps import get_current_user, get_current_user_flexible
from core import state
from core.enrichment import fetch_and_cache_ticker
from streaming.relay import broadcast_ui

router = APIRouter()
logger = logging.getLogger(__name__)


async def _backfill_ticker(ticker: str):
    """Fetch and broadcast ticker data in background."""
    try:
        tick = await fetch_and_cache_ticker(ticker)
        if tick:
            state.ticks[ticker] = tick
            await broadcast_ui({"type": "tick", "tick": tick})
    except Exception as e:
        logger.error("backfill %s failed: %s", ticker, e)


class TickerPatch(BaseModel):
    add: list[str] = []
    remove: list[str] = []


@router.get("/tickers/list")
async def get_tickers(current_user: str = Depends(get_current_user_flexible)):
    tickers = await db.get_user_tickers(current_user)
    return {"username": current_user, "tickers": tickers}


@router.post("/tickers/{ticker}")
async def add_ticker(ticker: str, current_user: str = Depends(get_current_user)):
    ticker = ticker.upper()
    try:
        await db.add_user_ticker(current_user, ticker)
    except ValueError:
        raise HTTPException(status_code=401, detail="user not found — please log out and register again")
    logger.info("%s added %s", current_user, ticker, extra={"tags": {"username": current_user, "action": "ticker_added", "ticker": ticker}})
    if ticker not in state.ticks:
        asyncio.create_task(_backfill_ticker(ticker))
    return {"message": "success"}


@router.delete("/tickers/{ticker}")
async def remove_ticker(ticker: str, current_user: str = Depends(get_current_user)):
    ticker = ticker.upper()
    await db.remove_user_ticker(current_user, ticker)
    logger.info("%s removed %s", current_user, ticker, extra={"tags": {"username": current_user, "action": "ticker_removed", "ticker": ticker}})
    return {"message": "success"}


@router.patch("/tickers")
async def patch_tickers(
    body: TickerPatch,
    current_user: str = Depends(get_current_user_flexible),
):
    add = [t.upper() for t in body.add]
    remove = [t.upper() for t in body.remove]
    await db.patch_user_tickers(current_user, add, remove)
    if add:
        logger.info("%s added %s", current_user, add, extra={"tags": {"username": current_user, "action": "ticker_added"}})
        for ticker in add:
            if ticker not in state.ticks:
                asyncio.create_task(_backfill_ticker(ticker))
    if remove:
        logger.info("%s removed %s", current_user, remove, extra={"tags": {"username": current_user, "action": "ticker_removed"}})
    return {"message": "success"}


@router.put("/tickers/order")
async def reorder_tickers(
    body: list[str],
    current_user: str = Depends(get_current_user),
):
    await db.reorder_tickers(current_user, [t.upper() for t in body])
    return {"message": "success"}


@router.get("/preferences")
async def get_preferences(current_user: str = Depends(get_current_user)):
    prefs = await db.get_preferences(current_user)
    return prefs


@router.put("/preferences")
async def set_preferences(
    body: dict,
    current_user: str = Depends(get_current_user),
):
    await db.set_preferences(current_user, body)
    return {"message": "success"}


@router.post("/api-key")
async def generate_api_key(current_user: str = Depends(get_current_user)):
    key = auth.generate_api_key()
    await db.store_api_key(current_user, auth.hash_api_key(key))
    logger.info("%s generated api key", current_user, extra={"tags": {"username": current_user, "action": "api_key_generated"}})
    return {"api_key": key, "note": "save this — it will not be shown again"}
