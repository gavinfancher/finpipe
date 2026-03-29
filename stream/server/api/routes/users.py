import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import server.auth as auth
import server.db as db
from server.api.deps import get_current_user, get_current_user_flexible
from server.pipeline import state
from server.pipeline.enrichment import _STATE_MAP, _fetch_closes, _trading_dates
from server.pipeline.relay import send_to_consumer

router = APIRouter()
logger = logging.getLogger(__name__)


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
    await send_to_consumer({"action": "subscribe", "ticker": ticker})
    if ticker not in state.prev_closes:
        closes = await _fetch_closes(ticker, _trading_dates())
        if closes["prev"] is not None:
            state.prev_closes[ticker] = closes["prev"]
        for period, attr in _STATE_MAP:
            if closes[period] is not None:
                getattr(state, attr)[ticker] = closes[period]
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
    if remove:
        logger.info("%s removed %s", current_user, remove, extra={"tags": {"username": current_user, "action": "ticker_removed"}})
    for ticker in add:
        await send_to_consumer({"action": "subscribe", "ticker": ticker})
        if ticker not in state.prev_closes:
            closes = await _fetch_closes(ticker, _trading_dates())
            if closes["prev"] is not None:
                state.prev_closes[ticker] = closes["prev"]
            for period, attr in _STATE_MAP:
                if closes[period] is not None:
                    getattr(state, attr)[ticker] = closes[period]
    return {"message": "success"}


@router.post("/api-key")
async def generate_api_key(current_user: str = Depends(get_current_user)):
    key = auth.generate_api_key()
    await db.store_api_key(current_user, auth.hash_api_key(key))
    logger.info("%s generated api key", current_user, extra={"tags": {"username": current_user, "action": "api_key_generated"}})
    return {"api_key": key, "note": "save this — it will not be shown again"}
