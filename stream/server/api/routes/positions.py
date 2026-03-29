import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import server.db as db
from server.api.deps import get_current_user
from server.pipeline import state
from server.pipeline.enrichment import _STATE_MAP, _fetch_closes, _trading_dates
from server.pipeline.relay import send_to_consumer

router = APIRouter()
logger = logging.getLogger(__name__)


class PositionCreate(BaseModel):
    ticker: str
    shares: float
    cost_basis: float


class PositionUpdate(BaseModel):
    shares: float
    cost_basis: float


@router.get("/positions")
async def get_positions(current_user: str = Depends(get_current_user)):
    return await db.get_positions(current_user)


@router.post("/positions")
async def add_position(body: PositionCreate, current_user: str = Depends(get_current_user)):
    ticker = body.ticker.upper()
    position = await db.add_position(current_user, ticker, body.shares, body.cost_basis)
    await send_to_consumer({"action": "subscribe", "ticker": ticker})
    if ticker not in state.prev_closes:
        closes = await _fetch_closes(ticker, _trading_dates())
        if closes["prev"] is not None:
            state.prev_closes[ticker] = closes["prev"]
        for period, attr in _STATE_MAP:
            if closes[period] is not None:
                getattr(state, attr)[ticker] = closes[period]
    logger.info("%s added position %s x%s @ %s", current_user, ticker, body.shares, body.cost_basis)
    return position


@router.patch("/positions/{position_id}")
async def update_position(position_id: int, body: PositionUpdate, current_user: str = Depends(get_current_user)):
    updated = await db.update_position(current_user, position_id, body.shares, body.cost_basis)
    if updated is None:
        raise HTTPException(status_code=404, detail="position not found")
    return updated


@router.delete("/positions/{position_id}")
async def delete_position(position_id: int, current_user: str = Depends(get_current_user)):
    deleted = await db.delete_position(current_user, position_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="position not found")
    logger.info("%s removed position %d", current_user, position_id)
    return {"message": "success"}
