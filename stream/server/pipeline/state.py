"""
Shared mutable state for the pipeline.
Imported by relay, enrichment, and API routes — mutate via module reference (state.ticks etc.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import websockets
    from fastapi import WebSocket

ticks: dict = {}
subscriptions: list[str] = []
prev_closes: dict[str, float] = {}
closes_5d: dict[str, float] = {}
closes_1m: dict[str, float] = {}
closes_3m: dict[str, float] = {}
closes_6m: dict[str, float] = {}
closes_1y: dict[str, float] = {}
closes_ytd: dict[str, float] = {}
closes_3y: dict[str, float] = {}
ui_clients: set[WebSocket] = set()
_consumer_ws: websockets.ClientConnection | None = None
