"""
Shared mutable state for the API/relay process.
Ticks are kept in-memory for WebSocket broadcast; perf data lives in Redis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket

ticks: dict = {}
subscriptions: list[str] = []
ui_clients: set[WebSocket] = set()
