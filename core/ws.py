from fastapi import WebSocket
from typing import List, Dict

class ConnectionManager:
    def __init__(self):
        # Храним активные соединения: {pc_id: websocket}
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, pc_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[pc_id] = websocket

    def disconnect(self, pc_id: int):
        if pc_id in self.active_connections:
            del self.active_connections[pc_id]

    async def send_command(self, pc_id: int, message: dict):
        if pc_id in self.active_connections:
            await self.active_connections[pc_id].send_json(message)

manager = ConnectionManager()
