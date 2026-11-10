from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect


class ConnectionManager:
    """Per-client bounded queues; drop oldest on overflow."""

    def __init__(self, maxsize: int = 100) -> None:
        self.maxsize = maxsize
        self._queues: dict[int, asyncio.Queue] = {}
        self._lock = asyncio.Lock()
        self._next_id = 0

    async def connect(self, websocket: WebSocket) -> int:
        await websocket.accept()
        async with self._lock:
            self._next_id += 1
            client_id = self._next_id
            self._queues[client_id] = asyncio.Queue(maxsize=self.maxsize)
        return client_id

    async def disconnect(self, client_id: int) -> None:
        async with self._lock:
            self._queues.pop(client_id, None)

    def publish(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, default=str)
        for queue in list(self._queues.values()):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                continue

    async def pump(self, websocket: WebSocket, client_id: int) -> None:
        queue = self._queues[client_id]
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20)
                    await websocket.send_text(payload)
                except asyncio.TimeoutError:
                    await websocket.send_text(json.dumps({"type": "ping"}))
        except WebSocketDisconnect:
            pass
        finally:
            await self.disconnect(client_id)
