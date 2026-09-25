"""In-memory WebSocket fan-out for live UI updates.

Event shape: {"type": "<event>", "data": {...}}
Types: message, node_update, position_update, radio_status, gateway_status, mqtt_status
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from app.logging_setup import get_logger

logger = get_logger()


class WebSocketManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)
        logger.info("WebSocket client connected (%s total)", len(self._clients))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)
        logger.info("WebSocket client disconnected (%s remaining)", len(self._clients))

    async def broadcast(self, event_type: str, data: dict[str, Any]) -> None:
        payload = {"type": event_type, "data": data}
        async with self._lock:
            clients = list(self._clients)
        stale: list[WebSocket] = []
        for client in clients:
            try:
                await client.send_json(payload)
            except Exception:
                stale.append(client)
        if stale:
            async with self._lock:
                for client in stale:
                    self._clients.discard(client)

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Thread-safe emit from radio / MQTT worker threads."""
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.broadcast(event_type, data), loop)
        except Exception as exc:
            logger.warning("WebSocket emit failed: %s", exc)


ws_manager = WebSocketManager()
