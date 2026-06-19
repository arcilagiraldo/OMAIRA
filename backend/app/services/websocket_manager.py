"""Manejador de conexiones WebSocket — con gestión por zona y límite global"""
from fastapi import WebSocket
from typing import Dict, List

MAX_CONEXIONES_TOTALES = 500


class ConnectionManager:
    def __init__(self):
        # zona_id → lista de websockets conectados a esa zona
        self.active_connections: Dict[str, List[WebSocket]] = {}

    def total_conexiones(self) -> int:
        return sum(len(v) for v in self.active_connections.values())

    async def connect(self, websocket: WebSocket, zona_id: str) -> bool:
        """Acepta la conexión si no se superó el límite global. Retorna True si conectó."""
        if self.total_conexiones() >= MAX_CONEXIONES_TOTALES:
            await websocket.close(code=4008, reason="Límite de conexiones alcanzado")
            return False
        await websocket.accept()
        self.active_connections.setdefault(zona_id, []).append(websocket)
        return True

    def disconnect(self, websocket: WebSocket, zona_id: str):
        conns = self.active_connections.get(zona_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self.active_connections.pop(zona_id, None)

    async def broadcast_zona(self, zona_id: str, message: dict):
        """Envía un mensaje a todos los clientes conectados a una zona específica."""
        for ws in list(self.active_connections.get(zona_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws, zona_id)
