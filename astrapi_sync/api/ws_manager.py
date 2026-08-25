# astrapi_sync/api/ws_manager.py
"""In-Process-Verbindungsmanager für die Sync-WebSockets.

Kein Redis/Message-Bus -- reicht für den Ein-Prozess-Deployment-Stil, den
alle bestehenden astrapi-Apps verwenden (ein uvicorn-Prozess pro App,
kein Multi-Worker). astrapi-core hatte dafür kein Vorbild (bislang keine
WebSockets in der Familie, nur eine SSE-Log-Tail-Route).
"""
import asyncio

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, folder_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.setdefault(folder_id, set()).add(ws)

    async def disconnect(self, folder_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(folder_id)
            if conns is not None:
                conns.discard(ws)
                if not conns:
                    self._connections.pop(folder_id, None)

    async def broadcast(self, folder_id: str, message: dict, exclude: WebSocket | None = None) -> None:
        async with self._lock:
            targets = list(self._connections.get(folder_id, ()))
        for ws in targets:
            if ws is exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()
