from fastapi import APIRouter, Depends, HTTPException, Request

from server.pipeline import state

router = APIRouter()


async def localhost_only(request: Request):
    if request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(status_code=403, detail="forbidden")


@router.get("/health", dependencies=[Depends(localhost_only)])
def health():
    return {
        "status": "ok",
        "relay_connected": state._consumer_ws is not None,
        "subscriptions": state.subscriptions,
        "tick_count": len(state.ticks),
        "ui_clients": len(state.ui_clients),
        "prev_closes_cached": len(state.prev_closes),
    }
