import logging

from fastapi import APIRouter, WebSocket

import core.auth as auth
from core import state

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: str = ""):
    username = auth.decode_token(token) if token else None
    if not username:
        await ws.close(code=4001)
        return
    await ws.accept()
    state.ui_clients.add(ws)
    logger.info("UI client connected (%s), pool=%d", username, len(state.ui_clients))
    try:
        if state.ticks:
            await ws.send_json({"type": "snapshot", "ticks": state.ticks})
        await ws.send_json({"type": "tickers", "tickers": state.subscriptions})
        while True:
            await ws.receive_text()
    except Exception:
        pass
    finally:
        state.ui_clients.discard(ws)
        logger.info("UI client disconnected (%s), pool=%d", username, len(state.ui_clients))


@router.websocket("/ws/demo")
async def ws_demo_endpoint(ws: WebSocket):
    await ws.accept()
    state.demo_clients.add(ws)
    logger.info("demo client connected, pool=%d", len(state.demo_clients))
    try:
        demo_ticks = {k: v for k, v in state.ticks.items() if k in state.DEMO_TICKERS}
        if demo_ticks:
            await ws.send_json({"type": "snapshot", "ticks": demo_ticks})
        await ws.send_json({"type": "tickers", "tickers": sorted(state.DEMO_TICKERS)})
        while True:
            await ws.receive_text()
    except Exception:
        pass
    finally:
        state.demo_clients.discard(ws)
        logger.info("demo client disconnected, pool=%d", len(state.demo_clients))
