import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import db
from api.deps import get_current_user
from pipeline import state
from pipeline.enrichment import fetch_and_cache_ticker
from pipeline.relay import broadcast_ui

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
    if ticker not in state.ticks:
        async def _backfill():
            try:
                tick = await fetch_and_cache_ticker(ticker)
                if tick:
                    state.ticks[ticker] = tick
                    await broadcast_ui({"type": "tick", "tick": tick})
            except Exception as e:
                logger.error("backfill %s failed: %s", ticker, e)
        asyncio.create_task(_backfill())
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
