from fastapi import APIRouter, Depends, HTTPException, Request

from core import state

router = APIRouter()


async def localhost_only(request: Request):
    if request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(status_code=403, detail="forbidden")


@router.get("/health", dependencies=[Depends(localhost_only)])
def health():
    return {
        "status": "ok",
        "subscriptions": state.subscriptions,
        "tick_count": len(state.ticks),
        "ui_clients": len(state.ui_clients),
    }
