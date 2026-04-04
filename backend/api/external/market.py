"""
Market status endpoint — public (no auth required).
"""

from fastapi import APIRouter
from common.market import get_market_status

router = APIRouter()


@router.get("/status")
async def market_status():
    return get_market_status()
